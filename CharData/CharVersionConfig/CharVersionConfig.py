import json
import typing
import logging
import warnings
from importlib import import_module
from typing import ClassVar, Dict, Callable, TYPE_CHECKING, Optional, List, Iterable, Deque, Final
from collections import deque

from CharData.CharVersionConfig.DataSourceDescription import DataSourceDescription
from CharData.CharVersionConfig.EditModes import EditModes
from CharData.CharVersionConfig.types import validate_strict_JSON_serializability, PythonConfigRecipe, PythonConfigRecipeDict,\
     ManagerInstructionsDictBase, ManagerInstructions, ManagerInstructionsDict, ManagerInstructionGroups

if TYPE_CHECKING:
    from CharData.BaseCharVersion import BaseCharVersion
    from CharData.DataSources.CharDataSourceBase import CharDataSourceBase
    from DBInterface.models import CharVersionModel
    # from DBInterface.DBCharVersion import DBCharVersion
from django.db import transaction

config_logger = logging.getLogger('chargen.CVConfig')


class CVConfig:
    """
    A CVConfig holds and manages metadata for a CharVersion.
    In particular, it is responsible for the construction of the list of data sources and managing the
    input pages / which LaTeX templates to use.

    It is determined by a JSON-string or equivalently its transformation into a python dict (called a recipe)
    adhering to a certain format, specified in types.py.

    Notably, it describes a list of instances (or a way to create those) of CVManagers that are responsible for all
    char-metadata related purposes. Modifying / adding / deleting CVManagers needs to go through the CVConfig interface.

    Furthermore, it holds some other metadata apart from managers: notably:
    Ordering of data sources (The managers define a *list* of data sources, but this is then re-ordered)
    TODO: Ordering of LaTeX output (dito)
    Edit mode

    The individual managers define hooks that are called at the appropriate time. E.g. when creating the list of data
    sources, we call appropriate functions on every manager.

    The ordering is added additionally, because the set of managers is treated as a *set of independent managers*.
    Inter-relations would require storing the ordering information in the managers, which is more complicated to keep
    track of.
    """

    # In order to serialize managers, we need to store a type-identifier in every ManagerInstruction.
    # For this, CVConfig maintains a dict known_types str -> Callable that is called to (re-)create the manager.
    # To fill this dict, callables need to register with CVConfig. This is done automatically upon import when
    # subclassing from BaseCVManager via a __init_subclass__ hook.
    known_types: ClassVar[Dict[str, Callable[..., 'BaseCVManager']]] = {}  # stores known type-identifiers and their callable.

    _python_recipe: PythonConfigRecipe
    _json_recipe: Optional[str]

    _edit_mode: EditModes  # enum type
    _managers: Optional[List['BaseCVManager']]
    _char_version: Optional['BaseCharVersion']  # weak-ref?
    _db_char_version: Optional['CharVersionModel']  # weak-ref?

    post_process_setup: Deque[Callable[[], None]]
    post_process_make_data_sources: Deque[Callable[[list], list]]
    post_process_validate: Deque[Callable[[], None]]

    post_process_copy_config: Deque[Callable[[PythonConfigRecipe], None]]  # Not setup in init!

    _data_source_descriptions: Optional[List[DataSourceDescription]]
    _data_sources: Optional[List['CharDataSourceBase']]

    def __init__(self, *, from_python: PythonConfigRecipe = None, from_json: str = None,
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
            _py_recipe_dict: PythonConfigRecipeDict = json.loads(self._json_recipe)
            self._python_recipe = PythonConfigRecipe.from_nested_dict(**_py_recipe_dict)
            self._edit_mode = self._python_recipe.edit_mode
        else:
            self._python_recipe = from_python
            self._edit_mode = from_python.edit_mode
            self._json_recipe = None  # Created on demand

        self.char_version = char_version
        # self.char_version's property setter may set self._db_char_version if char_version is of an appropriate type.
        # We check whether this matches db_char_version if provided

        if db_from_char := getattr(self, '_db_char_version', None):
            if db_char_version is not None and db_char_version != db_from_char:
                raise ValueError("both char_version and db_char_version provided with incompatible values.")
        else:
            self._db_char_version = db_char_version  # possibly None

        # TODO: Do we want this here or later? Note that post_process_copy_config is initialized later.
        self.post_process_setup = deque()
        self.post_process_make_data_sources = deque()
        self.post_process_validate = deque()

        self._managers = None
        self._data_source_descriptions = None
        self._data_sources = None
        if validate_syntax:
            self.validate_syntax(self._python_recipe)
        if create and not (validate_setup and setup_managers):
            # Note: We intentionally do not check self._db_char_version here. It is intended to be not None,
            # but we want to allow that for testing.
            # TODO: Check if that is actually used in testing.
            raise ValueError("create=True requires setup_managers and validate_setup to be set")
        if setup_managers:
            self.setup_managers(create=create)
        if validate_setup:
            if not setup_managers:
                raise ValueError("validate_setup = True requires setup_managers = True")
            try:
                self.validate_setup()
            except BaseException:
                config_logger.exception("Validation of CVConfig failed")
                raise

    @property
    def managers(self, /) -> List['BaseCVManager']:
        """
        Gets the list of managers. Note that we do not set up the managers on demand for now.
        """
        if self._managers is None:
            raise ValueError("Need to setup managers first")
        return self._managers

    @property
    def data_source_descriptions(self, /) -> List[DataSourceDescription]:
        """
        Get the list of data source descriptions. Requires the managers to have been set up before.
        """
        if self._data_source_descriptions is None:
            # This writes to _data_source_descriptions, so we only call this once.
            self.setup_data_source_descriptions()
        return self._data_source_descriptions

    @property
    def char_version(self, /) -> 'BaseCharVersion':
        """
        Gets the associated BaseCharVersion. This is needed, because some managers may need to access the CharVersion
        object.
        """
        if self._char_version is None:
            raise ValueError("No CharVersion associated to this config")
        return self._char_version

    @char_version.setter
    def char_version(self, new_value: 'BaseCharVersion', /) -> None:
        """
        Setter for char_version. If the new char_version is a DBCharVersion, it automatically sets _db_char_version as well.
        """
        self._char_version = new_value
        if hasattr(new_value, 'db_instance'):
            self._db_char_version = typing.cast('DBCharVersion', new_value).db_instance

    @property
    def db_char_version(self, /) -> 'CharVersionModel':
        if self._db_char_version is None:
            raise ValueError("No db entry associated to this config.")
        return self._db_char_version

    @property
    def json_recipe(self, /) -> str:
        if self._json_recipe is None:
            self._json_recipe = json.dumps(self._python_recipe.as_dict())
        return self._json_recipe

    @property
    def python_recipe(self, /) -> PythonConfigRecipe:
        return self._python_recipe

    @property
    def data_source_order(self, /) -> List[int]:
        return self.python_recipe.data_source_order

    @property
    def edit_mode(self, /) -> EditModes:
        return self._edit_mode

    def setup_managers(self, /, create: bool = False) -> None:
        """
        Sets up the list of managers. This needs to be called after setup to do anything useful.
        This creates the list of managers according to the recipe given by JSON / python dict using the callables
        registered with the Manager types.
        After that, we call post_process on every managers (this is so that post_process can inspect *other* managers
        or data set by them), then the post_process_setup queue.
        """
        cls = type(self)
        self._managers = []
        for manager_instruction in self.python_recipe.managers:
            type_id = manager_instruction.type_id
            if type_id not in cls.known_types:
                import_module(manager_instruction.module)
            new_manager: BaseCVManager = cls.known_types[type_id](*manager_instruction.args, **manager_instruction.kwargs, cv_config=self, manager_instruction=manager_instruction)
            if not isinstance(new_manager, BaseCVManager):
                raise ValueError("Invalid manager: Not derived from BaseCVManager")
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
            # Setup automatically?
            raise ValueError("Need to setup managers first")
        self._data_source_descriptions = []
        for manager in self._managers:
            self._data_source_descriptions += manager.data_source_descriptions

    def make_data_sources(self) -> List['CharDataSourceBase']:
        """
        Creates the lists of data_sources. Requires that setup_managers and setup_data_source_descriptions has been run.
        Data sources are created by querying managers. The order in which managers are queried is determined by
        data_source_order, which is a list of indexes in data_source_descriptions (We maintain the invariant that it
        is a permutation of data_source_descriptions, although this is not really needed here).
        """
        assert self._data_sources is None
        self._data_sources: list = list()
        for data_source_description_index in self.data_source_order:
            self.data_source_descriptions[data_source_description_index].make_and_append(target_list=self._data_sources)
        while self.post_process_make_data_sources:
            self._data_sources = self.post_process_make_data_sources.popleft()(self._data_sources)
        return self._data_sources

    @property
    def data_sources(self) -> List['CharDataSourceBase']:
        if self._data_sources is None:
            return self.make_data_sources()
        else:
            return self._data_sources

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
            new_edit_mode = self.edit_mode
        new_py_recipe = PythonConfigRecipe(edit_mode=new_edit_mode, data_source_order=self.data_source_order, managers=[])
        self.post_process_copy_config = deque()
        for manager in self.managers:
            manager.copy_config(new_py_recipe, transplant=transplant, target_db=target_db)
        while self.post_process_copy_config:
            self.post_process_copy_config.popleft()(new_py_recipe)
        new_config = CVConfig(from_python=new_py_recipe, validate_syntax=True, setup_managers=True)
        new_config.validate_setup()
        return new_config

    @classmethod
    def validate_syntax(cls, py: PythonConfigRecipe, /) -> None:
        """
        (Type-)Checks whether the python recipe has the correct form. Indicates failure by raising an exception.
        """
        if type(py) is not PythonConfigRecipe:
            raise ValueError("Invalid CVConfig: Wrong type")
        if type(py.edit_mode) is not EditModes:
            raise ValueError("Invalid CVConfig: Invalid edit mode")
        for manager_instruction in py.managers:
            if type(manager_instruction.args) is not list:
                raise ValueError("Invalid CVConfig: args of manager instruction is not list")
            validate_strict_JSON_serializability(manager_instruction.args)
            kwargs = manager_instruction.kwargs
            if type(kwargs) is not dict:
                raise ValueError("Invalid CVConfig: kwargs of manager instructions is not dict")
            validate_strict_JSON_serializability(kwargs)
            if 'cvconfig' in kwargs or 'manager_instruction' in kwargs:
                raise ValueError("Invalid CVConfig: contains internally used key")
            if type(manager_instruction.group) is not ManagerInstructionGroups:
                raise ValueError("Invalid CVConfig: group of manager instructions is unknown")
            if type(manager_instruction.module) is not str:
                raise ValueError("Invalid CVConfig: module is not string")
            if type(manager_instruction.type_id) is not str:
                raise ValueError("Invalid CVConfig: type_id is not string")

        if type(py.data_source_order) is not list:
            raise ValueError("Invalid CVConfig: data_source_order is not list")
        for entry in py.data_source_order:
            if (type(entry) is not int) or entry < 0:
                raise ValueError("Invalid CVConfig: data_source_order is not list of indices")
        data_source_order_copy = sorted(py.data_source_order)
        if data_source_order_copy != list(range(len(data_source_order_copy))):
            raise ValueError("Invalid CVConfig: data_source_order is not a permutation.", data_source_order_copy)

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


EMPTY_RECIPE_DICT: Final[PythonConfigRecipeDict] = {
    'edit_mode': EditModes.NORMAL,
    'data_source_order': [],
    'managers': []
}

EMPTY_RECIPE: Final[PythonConfigRecipe] = PythonConfigRecipe.from_nested_dict(**EMPTY_RECIPE_DICT)


class BaseCVManager:
    """
    Manager that does nothing. For testing and serves as base class.
    """

    # List of DataSourceDescriptions that is displayed to the user when this manager is present.
    # CVConfig.data_source_order is a permutation of indices into the list of all data_source_descriptions.
    # make_data_source is called for each data_source_description.
    data_source_descriptions: List[DataSourceDescription] = []
    # NOTE: Due to an __init_subclass__ hook that looks at __dict__, these do NOT get inherited to subclasses.
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

    def __init__(self, /, *args, cv_config: CVConfig, manager_instruction: ManagerInstructions, **kwargs):
        """
        Called by CVConfig.setup_managers() to initialize the manager
        :param cv_config: calling cv_config
        :param manager_instruction: refers to the entry in the calling cv_config's python_recipe.managers that was responsible for creating this.
        :param args: arbitrary arguments from the recipe.
        :param kwargs: arbitrary kw-arguments from the recipe.
        """
        self.args = args
        self.kwargs = kwargs
        self.cv_config = cv_config
        self.instructions = manager_instruction

    @classmethod
    def recipe_base_dict(cls) -> ManagerInstructionsDictBase:
        """
        This should be used in python recipes as {**CVManager.recipe_base(), ...} to set up type and module correctly.
        """
        ret: ManagerInstructionsDictBase = {'type_id': cls.type_id, 'module': cls.module}
        return ret

    def get_recipe_as_dict(self) -> ManagerInstructionsDict:
        """
        Used to re-create the arguments used to make this instance.
        Is almost identical to self.instructions (except that 'args' / 'kwargs' / 'type' / 'module' is always present
        and not defaulted)
        """
        return self.instructions.as_dict()

    def copy_config(self, target_recipe: PythonConfigRecipe, /, *, transplant: bool, target_db: Optional['CharVersionModel']) -> None:
        """
        Called for each manager on the source CharVersion when the containing CharVersion is copied.
        target_recipe is the python recipe for the new char with (new!) edit_mode and data_source_order already set.
        Its target_recipe.managers is initally empty.
        CVManager.copy_config is responsible for creating the corresponding entry in the target_recipe.
        transplant indicates whether we copy to a new CharModel
        target_db is the db entry of the new_char.

        self.cv_config.post_process_copy_config is a deque of callables(new_py_recipe) that is called after all
        copy_configs are run.

        Both copy_config and the the deque's callables modify its target_recipe argument.
        """
        target_recipe.managers.append(self.instructions.make_copy())

    def post_setup(self, create: bool = False) -> None:
        """
        Called after setup has finished for all managers
        """
        pass

    def get_data_sources(self, /, description: DataSourceDescription) -> Iterable['CharDataSourceBase']:
        return []

    def make_data_source(self, *, description: DataSourceDescription, target_list: List['CharDataSourceBase']) -> None:
        target_list.extend(self.get_data_sources(description))

    def validate_config(self):
        if self.instructions.module != type(self).module:
            raise ValueError("CVConfig validation failed: Registered module differs from saved module. Did you forget to create a db migration after a file rename during code reorganization?")
        if self.instructions.type_id != type(self).type_id:
            raise ValueError("CVConfig validation failed: Registered type_id differs from saved type_id. Did you forget to create a db migration after a rename of a CVManager class?")


BaseCVManager.__init_subclass__()  # BaseCVManager is a perfectly valid CVManager (that does absolutely nothing)
