import json
import typing
from typing import ClassVar, Dict, Callable, TYPE_CHECKING, Any, Optional, List, Iterable, Deque
from collections import deque
# from functools import wraps
if TYPE_CHECKING:
    from .BaseCharVersion import BaseCharVersion
    from .DataSources import CharDataSource
    from DBInterface.models import CharVersionModel
    # from DBInterface.DBCharVersion import DBCharVersion
import logging
import warnings
from django.db import transaction
from .EditModes import EditModes
from enum import Enum, auto
from importlib import import_module

config_logger = logging.getLogger('chargen.CVConfig')

class DataSourceDescription:
    """
    Class that describes a data source and that indicates how a user can interact with it in the CharVersion config
    settings. Should be subclassed. Note that this is purely for display purposes. The relevant state is held in the
    manager. In particular, we ask the manager to create a data source irrespective of whether active is set or not.
    It is the manager's job to not do anything if active == False.
    """
    movable: bool = True  # Can a user move the data source
    toggleable: bool = False  # Can a user toggle the data source from active / inactive
    active: bool = True  # Is the data source displayed as active? Note that this is purely for display purposes.
    description: str = ""  # Description that is displayed to the user

    # Position block of the data source. Data sources can only be moved within the blocks.
    class PositionType(Enum):
        start = auto()
        middle = auto()
        end = auto()
    position: PositionType = PositionType.middle

    # When adding a data source with priority != None, it will get its initial position within its block according to
    # priority.
    priority: Optional[int] = None
    manager: 'BaseCVManager'

    def make_and_append(self, target_list: list) -> None:
        self.manager.make_data_source(description=self, target_list=target_list)


class CVConfig:
    """
    A CVConfig holds and manages metadata for a CharVersion.
    In particular, it is responsible for the construction of the list of data sources and managing the
    input pages / which LaTeX templates to use.

    It is determined by a JSON-string or equivalently its transformation into a python dict (called a recipe)
    adhering to a certain format.

    Essentially, a recipe is a list of entries that contain 'type', 'module', 'args', 'kwargs', where type denotes an
    appropriate callable that is called with args and kwargs to construct the actual object (called a CVManager)
    that we are ultimately interested in. (We deal with recipes rather than the resulting objects because this is
    easier to serialize / make an UI for / update between versions of CharsheetGen). To make this work,
    CVConfig maintains a translation type->callable as a class variable that is filled by registering CVManager classes.

    Furthermore, the JSON objects contains some other metadata apart from managers, notably:
    Ordering of data source and LaTeX output (TODO)
    Edit mode

    TODO: More precise description
    Every CVManager provides a set of hooks that are called at the appropriate time. E.g. when creating the list of
    data source, we call manager.create_list(...) for every manager in the list of CVManagers in turn to create the data
    sources. CVConfig also acts as an interface for this list of managers.

    The recipe list of (type, args, kwargs) is organised into several sub-lists and each sub-list can
    add default args/kwargs to its entries. This is not visible in the list of CVManagers and is mostly for UI reasons.
    (Notably, editing the list of managers should be done in groups with a possibly different interface)

    The python representation of a recipe looks as follows:

    TODO: Redo
    recipe = {
        ... other Metadata (TODO)
        'edit_mode': True/False whether we are in edit mode

        'sub-list-id': [  #  'sub-list-id' may be e.g. 'data_sources'. We now give a list of source-specifiers.
            { # each source-specifier is a dict
                'type' : "some_string",  # type-identifier, see below
                'module' : "some module identifier", see below. This is imported if
                'args' : [some_JSON_able_list]   # args not present means empty list
                'kwargs' : {'some' : 'JSON_able_dict'}  # kwargs not present means empty dict
                ... # possibly other options may be added later
            }, ...
        ], ...
    }

    To achieve persistence in db, we need such a recipe to be serializable (we opt for JSON here).
    We restrict this further by requiring that all dict-keys are strings and we disallow floats.
    It is not recommended to use Non-ASCII characters in strings.
    (This means we allow None, bool, str, int as well as dicts and lists recursively built from that.
    Note that JSON is not able to distinguish object identity from equality, so with x=[], y=[], the difference between
    L1 = [x,x] and L2 = [x,y] is lost to JSON as well as references held to (subobjects of) recipes)
    """

    known_types: ClassVar[Dict[str, Callable]] = {}  # stores known type-identifiers and their callable.
    _python_recipe: dict
    _json_recipe: Optional[str]
    sub_recipes: ClassVar[list] = [  # name of recipe sub-lists that may appear
        # {'name': 'data_sources', 'args': [], 'kwargs': {}},
        {'name': 'defaults', 'args': [], 'kwargs': {}},
        {'name': 'core', 'args': [], 'kwargs': {}},
    ]
    _edit_mode: EditModes  # enum type
    _managers: Optional[List['BaseCVManager']]
    _char_version: Optional['BaseCharVersion']  # weak-ref?
    _db_char_version: Optional['CharVersionModel']  # weak-ref?

    post_process_setup: Deque[Callable[[], None]]
    post_process_make_data_sources: Deque[Callable[[list], list]]
    post_process_validate: Deque[Callable[[], None]]

    post_process_copy_config: Deque[Callable[[dict], None]]  # Not setup in init!


    _data_source_descriptions: Optional[List[DataSourceDescription]]

    def __init__(self, *, from_python: dict = None, from_json: str = None,
                 validate_syntax: bool = False, setup_managers: bool = True, validate_setup: bool = False,
                 char_version: 'BaseCharVersion' = None, db_char_version: 'CharVersionModel' = None,
                 create: bool = False):
        """
        Creates a CharVersionConfig object from either a python dict or from json.
        If validate_syntax is set, it will check whether the (computed or given) python dict adheres to the prescribed format.
        setup_managers indicates whether the registered managers will be set up. This is required for most uses.
        validate_setup (requires setup_managers) indicates whether some post-setup validation hooks should be run.
        char_version / db_char_version refers the the CharVersion object / db_char_version object that this configuration
        is attached to.
        create indicates that this object was just created. Only meaningful if requires setup and db_char_version is set
        It is communicated to the managers' post-setup hook, which may need to write some data to the database.
        """
        if (from_python is None) == (from_json is None):
            raise ValueError("Exactly one of from_python= or from_json= must be given and not be None.")
        if from_json is not None:
            self._json_recipe = from_json
            self._python_recipe = json.loads(self._json_recipe)
            # Type-cast int -> IntEnum  (JSON stores EditMode as int)
            self._edit_mode = self._python_recipe['edit_mode'] = EditModes(self.python_recipe['edit_mode'])
        else:
            self._python_recipe = from_python
            self._edit_mode = from_python['edit_mode']
            self._json_recipe = None  # Created on demand

        self.char_version = char_version
        # self.char_version's property setter may set self._db_char_version if char_version is of an appropriate type.
        # We check whether this matches db_char_version if provided

        if db_from_char := getattr(self, '_db_char_version', None):
            if db_char_version is not None and db_char_version != db_from_char:
                raise ValueError("both char_version and db_char_version provided with incompatible values.")
        else:
            self._db_char_version = db_char_version

        # TODO: Do we want this?
        self.post_process_setup = deque()
        self.post_process_make_data_sources = deque()
        self.post_process_validate = deque()

        self._managers = None
        self._data_source_descriptions = None
        if validate_syntax:
            self.validate_syntax(self.python_recipe)
        if create and not (validate_setup and setup_managers):
            # Note: We intentionally do not check self._db_char_version here. It is intended to be not None,
            # but we want to allow that for testing.
            raise ValueError("create=True requires setup_managers and validate_setup to be set")
        if setup_managers:
            self.setup_managers(create=create)
        if validate_setup:
            if not setup_managers:
                raise ValueError("validate_setup = True requires setup_managers = True")
            try:
                self.validate_setup()
            except ValueError:
                config_logger.exception("Validation of CVConfig failed")
                raise

    @property
    def managers(self) -> List['BaseCVManager']:
        if self._managers is None:
            raise ValueError("Need to setup managers first")
        return self._managers

    @property
    def data_source_descriptions(self) -> List[DataSourceDescription]:
        if self._data_source_descriptions is None:
            self.setup_data_source_descriptions()
        return self._data_source_descriptions

    @property
    def char_version(self) -> 'BaseCharVersion':
        if self._char_version is None:
            raise ValueError("No CharVersion associated to this config")
        return self._char_version

    @char_version.setter
    def char_version(self, /, new_value: 'BaseCharVersion'):
        self._char_version = new_value
        if hasattr(new_value, 'db_instance'):
            self._db_char_version = typing.cast('DBCharVersion', new_value).db_instance

    @property
    def db_char_version(self) -> 'CharVersionModel':
        if self._db_char_version is None:
            raise ValueError("No db entry associated to this config.")
        return self._db_char_version

    @property
    def json_recipe(self) -> str:
        if self._json_recipe is None:
            self._json_recipe = json.dumps(self.python_recipe)
        return self._json_recipe

    @property
    def python_recipe(self) -> dict:
        return self._python_recipe

    @property
    def data_source_order(self) -> List[int]:
        return self.python_recipe['data_source_order']

    @property
    def edit_mode(self) -> EditModes:
        return self._edit_mode

    @classmethod
    def register(cls, type_id: str, creator: Callable, *, allow_overwrite: bool = False) -> None:
        """
        Registers the callable (typically a class) creator with the given type_id. This then makes it possible to
        use this string as a type in recipes to create managers using the given creator.
        You need to set allow_overwrite=True to allow re-registering a given type_id with a new, different creator.
        """
        if type_id in cls.known_types:  #
            if cls.known_types[type_id] == creator:
                config_logger.info("Re-registering CVManager %s with same creator" % type_id)
                return
            else:
                if allow_overwrite:
                    config_logger.info("Re-registering CVManager %s with new creator, as requested" % type_id)
                else:
                    config_logger.critical("Trying to re-register CVManager %s with new creator, failing." % type_id)
                    raise ValueError("Type identifier %s is already registered with a different creator" % type_id)
        cls.known_types[type_id] = creator
        config_logger.info("Registered CV %s" % type_id)

    # # processors can call this to add functions to the queue. These are then called after some processors have run.
    # def add_to_end_of_post_process_queue(self, fun: Callable[[Any], Any], /):
    #     self.post_process.append(fun)
    #
    # def add_to_front_of_post_process_queue(self, fun: Callable[[Any], Any], /):
    #     self.post_process.appendleft(fun)
    #
    # def handle_post_processing_queue(self, arg, /):
    #     while self.post_process:
    #         arg = self.post_process.popleft()(arg)
    #     return arg

    # def run_on_managers(self, method_name: str, /, *args, **kwargs):
    #     if self.managers is None:
    #         raise ValueError("Need to setup managers first")
    #     for manager in self.managers:
    #         if fun := getattr(manager, method_name, None):
    #             fun(*args, **kwargs)
    #         else:
    #             # This should not happen because we define the relevant methods as no-ops in a base class.
    #             # TODO: Consider simplifying this
    #             config_logger.critical("method name %s not found in manager", method_name)

    if TYPE_CHECKING:
        @staticmethod
        def validate_JSON_serializability(arg: Any) -> None:  # For static type checkers that look at the first definition.
            """
            Checks whether arg is a python object that adheres to our JSON-serializability restrictions.
            (Note that we are stricter that JSON proper). In case of non-adherence, we raise a ValueError.
            """
    else:
        # noinspection PyMethodParameters,PyMethodMayBeStatic
        def validate_JSON_serializability() -> Callable:  # creator-function to make recursion work without reference to the containing class, lack of self-parameter is correct.
            def real_validate_JSON_serializability(arg):
                """
                Checks whether arg is a python object that adheres to our JSON-serializability restrictions.
                (Note that we are stricter that JSON proper). In case of non-adherence, we raise a ValueError.
                """
                if (arg is None) or type(arg) in [int, bool, str]:
                    return
                elif type(arg) is list:  # No sub-typing! Also, fail on tuples.
                    for item in arg:
                        real_validate_JSON_serializability(item)
                    return
                elif type(arg) is dict:
                    for key, value in arg.items():
                        if type(key) is not str:
                            raise ValueError("Invalid CVConfig: non-string dict key")
                        real_validate_JSON_serializability(value)
                    return
                else:
                    raise ValueError("Invalid CVConfig: Contains non-allowed python type")
            return real_validate_JSON_serializability
        validate_JSON_serializability = staticmethod(validate_JSON_serializability())

    @classmethod
    def validate_syntax(cls, /, py: dict) -> None:
        """
        (Type-)Checks whether the python recipe has the correct form. Indicates failure by raising an exception.
        """
        if type(py) is not dict:
            raise ValueError("Invalid CVConfig: Not a dict")
        try:
            if type(py['edit_mode']) is not EditModes:
                raise ValueError("Invalid CVConfig: Invalid edit mode")
        except KeyError:
            raise ValueError("Invalid CVConfig: edit_mode not set")
        try:
            py['edit_mode'] = int(py['edit_mode'])
            cls.validate_JSON_serializability(py)
        finally:
            py['edit_mode'] = EditModes(py['edit_mode'])
        try:
            if type(py['data_source_order']) is not list:
                raise ValueError("Invalid CVConfig: data_source_order is not list")
            for entry in py['data_source_order']:
                if (type(entry) is not int) or entry < 0:
                    raise ValueError("Invalid CVConfig: data_source_order is not list of indices")
        except KeyError:
            raise ValueError("Invalid CVConfig: Missing data_source_order")
        for sub_recipe_spec in cls.sub_recipes:
            sub_recipe_list = py.get(sub_recipe_spec['name'], [])
            if type(sub_recipe_list) is not list:
                raise ValueError("Invalid CVConfig: Individual sub-lists must be lists")
            for ingredient in sub_recipe_list:
                if type(ingredient) is not dict:
                    raise ValueError("Invalid CVConfig: Individual entries of recipe sub-lists must be dicts")
                try:
                    module= ingredient['module']
                except KeyError:
                    raise ValueError("Invalid CVConfig: entry lack module argument")
                if type(module) is not str:
                    raise ValueError("Invalid CVConfig: entry has non-string module argument")
                try:
                    if type_id := ingredient['type'] not in cls.known_types:
                        import_module(module)
                        if type_id not in cls.known_types:
                            raise ValueError("Invalid CVConfig: entry has an unknown 'type' argument %s" % type_id)
                except KeyError:
                    raise ValueError("Invalid CVConfig: Entry lacks a type")
                if type(ingredient.get('args', [])) is not list:
                    raise ValueError("Invalid CVConfig: Entry's args are not list")
                if type(ingredient.get('kwargs', {})) is not dict:
                    raise ValueError("Invalid CVConfig: Entry's kwargs are not dict")

    def setup_managers(self, create: bool = False):
        """
        Sets up the list of managers. This needs to be called after setup to do anything useful.
        This creates the list of managers according to the recipe given by JSON / python dict using the callables
        registered with the Manager types.
        After that, we call post_process on every managers (this is so that post_process can inspect *other* managers
        or data set by them), then the post_process_setup queue.
        """
        cls = type(self)
        self._managers = []
        for sub_recipe_spec in cls.sub_recipes:
            sub_recipe_list = self.python_recipe.get(sub_recipe_spec['name'], [])
            default_args = sub_recipe_spec['args']
            default_kwargs = sub_recipe_spec['kwargs']
            for ingredient in sub_recipe_list:
                args: list = list(default_args)
                args += ingredient.get('args', [])
                kwargs: dict = dict(default_kwargs)  # must not and does not contain 'cv_config' / 'recipe' / 'recipe_type'
                # Note that we do not have to validate this, as it would just be ignored.
                kwargs['cv_config'] = self
                kwargs['recipe'] = ingredient
                kwargs['recipe_type'] = sub_recipe_spec['name']
                kwargs.update(ingredient.get('kwargs', {}))
                type_id = ingredient['type']
                if type_id not in cls.known_types:
                    import_module(ingredient['module'])
                new_manager = cls.known_types[type_id](*args, **kwargs)
                if not isinstance(new_manager, BaseCVManager):
                    raise ValueError("Invalid manager: Not derived from BaseCVManager.")
                self._managers.append(new_manager)
        for manager in self.managers:
            manager.post_setup(create=create)
        while self.post_process_setup:
            self.post_process_setup.popleft()()

    def setup_data_source_descriptions(self):
        """
        Sets up the list of data source descriptions.
        Called automatically upon access of data_source_descriptions
        """
        if self._managers is None:
            raise ValueError("Need to setup managers first")
        self._data_source_descriptions = []
        for manager in self._managers:
            self._data_source_descriptions += manager.data_source_descriptions

    def make_data_sources(self) -> List['CharDataSource']:
        """
        Creates the lists of data_sources. Requires that setup_managers and setup_data_source_descriptions has been run.
        Data sources are created by querying managers. The order in which managers are queried is determined by
        data_source_order, which is a list of indexes in data_source_descriptions (We maintain the invariant that it
        is a permutation of data_source_descriptions, although this is not really needed here).
        """
        data_sources: list = list()
        for data_source_description_index in self.data_source_order:
            self.data_source_descriptions[data_source_description_index].make_and_append(target_list=data_sources)
        while self.post_process_make_data_sources:
            data_sources = self.post_process_make_data_sources.popleft()(data_sources)
        return data_sources

    def validate_setup(self) -> None:
        """
        Run every managers validation method (which can access the full config).
        Intended to be run directly after setup_managers()
        Indicates Errors by raising ValueError
        """
        for manager in self.managers:
            manager.validate_config()
        while self.post_process_validate:
            self.post_process_validate.popleft()()
        data_source_order_copy = sorted(self.data_source_order)
        if data_source_order_copy != list(range(len(self.data_source_descriptions))):
            raise ValueError("data_source_order is not a permutation of data_source_descriptions")
        return

    def copy_config(self, *, target_db: Optional['CharVersionModel'], new_edit_mode: Optional[EditModes], transplant: bool) -> 'CVConfig':
        """
        Creates a new CVConfig from the current one. target_db is the new CharVersionModel this is associated to.
        (target_db == None is for testing only)
        Note that target_db must already be present in the db: copy_config should always be run in a transaction anyway,
        and the caller should just save target_db prior to calling copy_config.
        new_edit_mode is whether we set edit mode for the new char. None to copy previous value.
        Transplant indicates whether the new CVConfig is for a different CharModel than the source.

        Note that copy_config does NOT save the resulting new CVConfig in the DB. Managers may save data in the db
        associated to the new CharVersion, though.
        """
        if (target_db is not None) and transaction.get_autocommit():
            raise warnings.warn("copy_config should be wrapped in a transaction.", RuntimeWarning)
        if new_edit_mode is None:
            new_py_recipe = {'edit_mode': self.edit_mode}
        else:
            new_py_recipe = {'edit_mode': new_edit_mode}
        new_py_recipe['data_source_order'] = list(self.data_source_order)
        self.post_process_copy_config = deque()
        for manager in self.managers:
            manager.copy_config(new_py_recipe, new_edit_mode=new_edit_mode, transplant=transplant, target_db=target_db)
        while self.post_process_copy_config:
            self.post_process_copy_config.popleft()(new_py_recipe)
        new_config = CVConfig(from_python=new_py_recipe, validate_syntax=True, setup_managers=True)
        new_config.validate_setup()
        return new_config

EMPTY_RECIPE = {
    'edit_mode': EditModes.NORMAL,
    'data_source_order': [],
}


class BaseCVManager:
    """
    Manager that does nothing. For testing and serves as base class.
    """

    # List of DataSourceDescriptions that is displayed to the user when this manager is present.
    # CVConfig.data_source_order is a permutation of indices into the list of all data_source_descriptions.
    # make_data_source is called for each data_source_description.
    data_source_descriptions: List[DataSourceDescription] = []
    module: ClassVar[str]  # Set to cls.__module__ (after class creation).
    type_id: ClassVar[str]  # Set to cls.__name__ (after class creation).

    # Called manually for BaseCVManager itself.
    def __init_subclass__(cls, module: str = None, type_id: str = None, register: bool = True, **kwargs):
        super().__init_subclass__(**kwargs)
        if module is not None:
            if m:=cls.__dict__.get('module') is not None:
                assert m == module
            cls.module = module
        if cls.__dict__.get('module') is None:
            cls.module = cls.__module__

        if type_id is not None:
            if t:=cls.__dict__.get('type_id') is not None:
                assert t == type_id
            cls.type_id = type_id
        if cls.__dict__.get('type_id') is None:
            cls.type_id = cls.__name__
        if register:
            CVConfig.register(type_id=cls.type_id, creator=cls)

    @classmethod
    def recipe_base(cls):
        """
        This should be used in python recipes as {**CVManager.recipe_base(), ...} to set up type and module correctly.
        """
        return {'type': cls.type_id, 'module': cls.module}

    def make_recipe(self):
        return {**type(self).recipe_base(), 'args': self.args, 'kwargs': self.kwargs}

    def __init__(self, cv_config: CVConfig, recipe: dict, recipe_type: str, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.cv_config = cv_config
        self.instructions = recipe
        self.recipe_type = recipe_type

    def copy_config(self, target_recipe: dict, /, *, new_edit_mode: EditModes, transplant: bool, target_db: Optional['CharVersionModel']) -> None:
        """
        Called for each manager on the source CharVersion when the containing CharVersion is copied.
        target_recipe is the python recipe for the new char.
        CVManager.copy_config is responsible for creating the corresponding entry in the target_recipe.
        new_edit_mode indicates whether edit_mode was changed and to what.
        transplant indicates whether we copy to a new CharModel
        target_db is the db entry of the new_char.

        self.cv_config.post_process_copy_config is a deque of callables(new_py_recipe) that is called after all
        copy_configs are run.
        """
        if self.recipe_type not in target_recipe:
            target_recipe[self.recipe_type] = list()
        new_recipe = dict(self.instructions)
        target_recipe[self.recipe_type].append(new_recipe)

    def post_setup(self, create: bool = False) -> None:
        """
        Called after setup has finished for all managers
        """
        pass

    def get_data_sources(self, description: DataSourceDescription) -> Iterable['CharDataSource']:
        return []

    def make_data_source(self, *, description: DataSourceDescription, target_list: List['CharDataSource']) -> None:
        target_list.extend(self.get_data_sources(description))

    def validate_config(self):
        pass


BaseCVManager.__init_subclass__()

# BaseCVManager.module = BaseCVManager.__module__

# CVConfig.register('base', BaseCVManager)
