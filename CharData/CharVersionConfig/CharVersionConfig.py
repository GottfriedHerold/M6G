from __future__ import annotations
import json
import typing
import logging
import warnings
from importlib import import_module
from typing import ClassVar, Dict, Callable, TYPE_CHECKING, Optional, List, Deque, Literal, Tuple, Union
from collections import deque

from django.db import transaction
from django.conf import settings as django_settings

from .EditModes import EditModes
from .types import validate_strict_JSON_serializability, PythonConfigRecipe, PythonConfigRecipeDict, \
    ManagerInstructionGroups, CreateManagerEnum, ManagerInstructions

if TYPE_CHECKING:
    from CharData.BaseCharVersion import BaseCharVersion
    from CharData.DataSources.CharDataSourceBase import CharDataSourceBase
    from DBInterface.models import CharVersionModel
    from .BaseCVManager import BaseCVManager
    from .DataSourceDescription import DataSourceDescription
    from DBInterface.DBCharVersion import DBCharVersion


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
    _managers: Optional[List[BaseCVManager]]
    _char_version: Optional[BaseCharVersion]  # weak-ref?
    _db_char_version: Optional[CharVersionModel]  # weak-ref?

    post_process_setup: Deque[Callable[[], None]]
    post_process_make_data_sources: Deque[Callable[[list], list]]
    post_process_validate: Deque[Callable[[], None]]

    post_process_copy_config: Deque[Callable[[PythonConfigRecipe], None]]  # Not setup in init!

    _data_source_descriptions: Optional[List[DataSourceDescription]]
    # Note: @property data_source_order is taken from _python_recipe.
    _data_sources: Optional[List[CharDataSourceBase]]

    # TODO: Output ordering

    def __init__(self, *, from_python: PythonConfigRecipe = None, from_json: str = None,
                 char_version: BaseCharVersion = None, db_char_version: CharVersionModel = None,
                 setup_managers: bool,
                 validate_syntax: bool = False, validate_setup: bool = False):
        """
        Creates a CharVersionConfig object from either a python dict or from json.
        If validate_syntax is set, it will check whether the (computed or given) python dict adheres to the prescribed format.
        setup_managers indicates whether the registered managers will be set up. This is required for most uses.
        validate_setup (requires setup_managers) indicates whether some post-setup validation hooks should be run.
        char_version / db_char_version refers the the CharVersion object / db_char_version object that this configuration
        is initially attached to.
        """
        if (from_python is None) == (from_json is None):
            raise ValueError("Exactly one of from_python= or from_json= must be given and not be None.")
        self._make_clean(from_python=from_python, from_json=from_json,
                         char_version=char_version, db_char_version=db_char_version)
        if validate_syntax:
            self.validate_syntax(self._python_recipe)
        if setup_managers:
            self.setup_managers()
        if validate_setup:
            self.validate_setup()

    @classmethod
    def create_char_version_config(cls, *, from_python: PythonConfigRecipe = None, from_json: str = None,
                                   char_version: BaseCharVersion = None, db_char_version: CharVersionModel = None,
                                   setup_managers: Literal[True]) -> CVConfig:
        """
        Creates a new char_version_config.

        Note that the difference to calling CVConfig(...) is that CVConfig provides an interface to a Config which
        is serialized in the database, whereas create_char_version_config is used to create it.
        It calls on-create hooks on the managers, which may touch the database. Create_char_version_config itself
        does NOT touch the database.

        This should be called EXACTLY ONCE for a given (db version of) char_version config and the result saved in the db.

        The db_char_version entry should already exist in the db (but can or should be a minimal or dummy entry) and
        its config entry will have to be overwritten using the result of this call. This is needed because managers may
        need to create db references to db_char_version.
        """
        assert setup_managers  # for now. Create_char_version_config always runs setup, essentially just to run checks.
        if transaction.get_autocommit():  # Essentially always a bug. Note that django.test.TestCase wraps everything.
            config_logger.critical("Calling create_char_version_config outside a transaction")
            warnings.warn("create_char_version_config should be wrapped in a transaction.", RuntimeWarning)
        new_char_version_config = cls(from_python=from_python, from_json=from_json,
                                      char_version=char_version, db_char_version=db_char_version,
                                      setup_managers=False, validate_setup=False,
                                      validate_syntax=True)
        if new_char_version_config.db_char_version is None:  # This makes little sense outside of specific testing instances.
            if django_settings.TESTING_MODE:
                config_logger.info('Called create_char_version_config without an associated db entry')
            else:
                config_logger.critical("Called create_char_version_config without an associated db entry.")
        new_char_version_config.setup_managers(create=CreateManagerEnum.create_config)
        new_char_version_config._re_init(setup_managers=setup_managers)
        return new_char_version_config

    def destroy_char_version_config(self) -> None:
        """
        Should be run when the char_version_config is to be deleted from the database. This informs manager
        that they should do some cleanup (typically not required)
        """
        if transaction.get_autocommit():  # Essentially always a bug. Note that django.test.TestCase wraps everything.
            config_logger.critical("Calling destroy_char_version_config outside a transaction")
            warnings.warn("destroy_char_version_config should be wrapped in a transaction.", RuntimeWarning)
        if self.db_char_version is None:  # This makes little sense outside of specific testing instances.
            if django_settings.TESTING_MODE:
                config_logger.info('Called destroy_char_version_config without an associated db entry')
            else:
                config_logger.critical("Called destroy_char_version_config without an associated db entry.")
        self._re_init(setup_managers=False)
        self.setup_managers(create=CreateManagerEnum.destroy_config)

    def _re_init(self, *, setup_managers: bool) -> None:
        """
        Resets the cv_config into an initial state as if it was just created with the given parameters
        (with from_python=self.python_recipe)
        Validation is always run, as this is essentially only called whenever the config changes.

        Note: char_version and db_char_version have no default (because both None and "use old params" are meaningful).
        As this is an internal interface, we are explicit here.
        """
        if self.post_process_setup or self.post_process_validate or self.post_process_make_data_sources:
            config_logger.critical("Post-process queue not empty when calling _re_init")
            warnings.warn("Post-process queue not empty", RuntimeWarning)
        self._make_clean(from_python=self.python_recipe, char_version=self._char_version, db_char_version=self._db_char_version)
        self.validate_syntax(self._python_recipe)
        if setup_managers:
            self.setup_managers()
            self.validate_setup()

    def _make_clean(self, *, from_python: Optional[PythonConfigRecipe] = None, from_json: Optional[str] = None,
                    char_version: BaseCharVersion, db_char_version: CharVersionModel) -> None:
        """
        Puts the char_version in a valid pristine state, no matter what state it was in before.
        Managers are not setup yet, so the only usable feature is JSON <-> Python description serialization.

        :param from_python: python configuration for the manager. Exactly one of this and from_json must be set.
        :param from_json: JSON configuration for the manager. Exactly one of this and from_python must be set.
        :param char_version: char_version object (interface for actual data) associated. May be None and can be set later.
        :param db_char_version: char_version_model in DB that this config is associated with. May be None and can be set later.
        :return: None
        """
        if (from_python is None) == (from_json is None):
            raise ValueError("Exactly one of from_python= or from_json= must be given and not be None.")
        self._setup_recipe(from_python=from_python, from_json=from_json)
        self._associate_initial_char_version(char_version=char_version, db_char_version=db_char_version)
        self._setup_queues()
        self._clear_managed_data()

    def _setup_recipe(self, from_python: PythonConfigRecipe = None, from_json: str = None) -> None:
        """
        Sets up the recipe information contained in the char version, converting Python <- JSON.
        """
        if from_json is not None:
            self._json_recipe = from_json
            _py_recipe_dict: PythonConfigRecipeDict = json.loads(self._json_recipe)
            self._python_recipe = PythonConfigRecipe.from_nested_dict(**_py_recipe_dict)
            self._edit_mode = self._python_recipe.edit_mode
        else:
            self._python_recipe = from_python
            self._edit_mode = from_python.edit_mode
            self._json_recipe = None  # Created on demand

    def _associate_initial_char_version(self, char_version: BaseCharVersion = None, db_char_version: CharVersionModel = None) -> None:
        """
        Associates the given char_version and db_char_version to the given config.
        db_char_version is inferred from char_version, if possible.
        This function does not care about previous assignments, if any.
        """
        self._char_version = char_version
        try:  # infer db_char_version from char_version, if possible (and check that it is compatible with db_char_version)
            char_version: DBCharVersion  # May be actually the case.
            # may fail with AttributeError (including char_version == None case). char_version.db_instance == None is OK.
            self._db_char_version = char_version.db_instance
            if db_char_version and db_char_version != self._db_char_version:
                raise ValueError("Provided char_version's db version and directly provided db_char_version do not match")
        except AttributeError:  # char_version is None or BaseCharVersion.
            self._db_char_version = db_char_version

    def associate_char_version(self, char_version: BaseCharVersion = None, db_char_version: CharVersionModel = None) -> None:
        """
        Associates the given char_version and db_char_version to the given config.
        The difference to _associate_initial_char_version is that the above is called when creating a cv_config, whereas
        associate_char_version may be called later on an existing config to associate it with a db entry.
        This is done to simplify avoiding circular dependencies associating db, char_version and config with each other.

        For now, can only be called pre-setup. Also, cannot un-associate, only strengthen.
        (We would need to inform managers otherwise)
        """
        assert self._managers is None  # Otherwise, we would need to call a hook on the managers.
        old_char_version = self._char_version
        old_db_char_version = self._db_char_version
        self._associate_initial_char_version(char_version=char_version, db_char_version=db_char_version)
        if (old_char_version and (old_char_version != self._char_version)) or (old_db_char_version and (old_db_char_version != self._db_char_version)):
            raise ValueError("associate_char_version called with char_version/db_char_version incompatible with previous association")

    def _setup_queues(self, /) -> None:
        # TODO: Do we want this during init? Note that post_process_copy_config is initialized later.
        self.post_process_setup = deque()
        self.post_process_make_data_sources = deque()
        self.post_process_validate = deque()

    def _clear_managed_data(self, /) -> None:
        self._managers = None
        self._data_source_descriptions = None
        self._data_sources = None

    @property
    def managers(self, /) -> List[BaseCVManager]:
        """
        Gets the list of managers. Note that we do not set up the managers on demand for now.
        """
        if self._managers is None:
            raise ValueError("Need to setup managers first")
        return self._managers

    def setup_managers(self, /, create: CreateManagerEnum = CreateManagerEnum.no_create) -> None:
        """
        Sets up the list of managers. This needs to be called after setup to do anything useful.
        This creates the list of managers according to the recipe given by JSON / python dict using the callables
        registered with the Manager types.
        After that, we call post_process on every managers (this is so that post_process can inspect *other* managers
        or data set by them), then the post_process_setup queue.
        """
        if self._managers is not None:
            raise ValueError("Trying to set up managers multiple times")
        self._managers = []
        for manager_instruction in self.python_recipe.managers:
            self._managers.append(self._create_manager_from_instruction(manager_instruction))
        for manager in self.managers:
            manager.post_setup(create=create)
        while self.post_process_setup:
            self.post_process_setup.popleft()()

    @property
    def data_source_descriptions(self, /) -> List[DataSourceDescription]:
        """
        Get the list of data source descriptions. Requires the managers to have been set up before.
        """
        if self._data_source_descriptions is None:
            # This writes to _data_source_descriptions, so we only call this once.
            self._setup_data_source_descriptions()
        return self._data_source_descriptions

    @property
    def char_version(self, /) -> BaseCharVersion:
        """
        Gets the associated BaseCharVersion. This is needed, because some managers may need to access the CharVersion
        object.
        """
        if self._char_version is None:
            raise ValueError("No CharVersion associated to this config")
        return self._char_version

    @property
    def db_char_version(self, /) -> CharVersionModel:
        """
        Gets the associated DB char version. Note that you might need to reload this from db, as it might be stale.
        This mainly is for storing the primary db key.
        """
        if self._db_char_version is None:
            raise ValueError("No db entry associated to this config.")
        return self._db_char_version

    @property
    def json_recipe(self, /) -> str:
        """
        Gets a JSON string which allows reconstructing self.
        """
        if self._json_recipe is None:
            self._json_recipe = json.dumps(self._python_recipe.as_dict())
        return self._json_recipe

    @property
    def python_recipe(self, /) -> PythonConfigRecipe:
        """
        Gets a python object which allows reconstructing self.
        """
        return self._python_recipe

    @property
    def data_source_order(self, /) -> List[int]:
        """
        Gets the data source ordering. The result is a permutation of indices into self.data_source_descriptions.
        :return:
        """
        return self.python_recipe.data_source_order

    @property
    def edit_mode(self, /) -> EditModes:
        return self._edit_mode

    def _create_manager_from_instruction(self, manager_instruction: ManagerInstructions, /) -> BaseCVManager:
        type_id = manager_instruction.type_id
        if type_id not in type(self).known_types:
            import_module(manager_instruction.module)
        # TODO: Type-Check that return type is correct?
        return type(self).known_types[type_id](*manager_instruction.args, **manager_instruction.kwargs, cv_config=self, manager_instruction=manager_instruction)

    def find_data_source_description(self, data_source_desc: DataSourceDescription, /) -> Tuple[int, int]:
        """
        Finds the index of data_source_desc in the list of data source descriptions.
        Returns a tuple (i,j) s.t. data_source_order[i] == j and data_source_descriptions[j] is data_source_desc.
        Note that the latter comparison is by identity.
        """
        if self._managers is None or self._data_source_descriptions is None:
            raise ValueError("find data_source_description requires setup.")
        data_source_order = self.data_source_order
        data_source_descriptions = self.data_source_descriptions
        for i in range(len(self._data_source_descriptions)):
            if data_source_descriptions[data_source_order[i]] is data_source_desc:
                return i, data_source_order[i],
        else:
            raise ValueError("data source description not found")

    def _setup_data_source_descriptions(self, /):
        """
        Sets up the list of data source descriptions.
        Called automatically upon access of data_source_descriptions
        """
        if self._managers is None:
            # Setup automatically?
            raise ValueError("Need to setup managers first")
        assert self._data_source_descriptions is None
        self._data_source_descriptions = []
        for manager in self._managers:
            self._data_source_descriptions += manager.data_source_descriptions

    def make_data_sources(self, /) -> List[CharDataSourceBase]:
        """
        Creates the lists of data_sources. Requires that setup_managers has been run.
        Data sources are created by querying managers. The order in which managers are queried is determined by
        data_source_order, which is a list of indexes in data_source_descriptions (We maintain the invariant that it
        is a permutation of data_source_descriptions, although this is not really needed here).
        """
        assert self._data_sources is None
        self._data_sources: list = list()
        for data_source_description_index in self.data_source_order:
            self.data_source_descriptions[data_source_description_index].make_and_append_to(target_list=self._data_sources)
        while self.post_process_make_data_sources:
            self._data_sources = self.post_process_make_data_sources.popleft()(self._data_sources)
        return self._data_sources

    @property
    def data_sources(self, /) -> List[CharDataSourceBase]:
        """
        Gets the data sources defined by the current config.

        These are created using the managers: Each manager defines a list/set of data source (descriptions)
        and we use self._data_source_order to correctly order them.
        """
        if self._data_sources is None:
            return self.make_data_sources()
        else:
            return self._data_sources

    def validate_setup(self, /) -> None:
        """
        Run every managers validation method (which can access the full config).
        Intended to be run directly after setup_managers()
        Indicates Errors by raising ValueError
        """
        try:
            for manager in self.managers:
                manager.validate_config()
            while self.post_process_validate:
                self.post_process_validate.popleft()()
            data_source_order_copy = sorted(self.data_source_order)
            if data_source_order_copy != list(range(len(self.data_source_descriptions))):
                raise ValueError("data_source_order is not a permutation of data_source_descriptions")
        except Exception:
            # This also logs the exception.
            config_logger.exception("Validation of CVConfig failed")
            raise
        # TODO: Sortedness of data-source description according to group
        return

    def copy_config(self, *, target_db: Optional[CharVersionModel], new_edit_mode: Optional[EditModes], transplant: bool) -> CVConfig:
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

    def add_manager(self, manager_instruction: ManagerInstructions, /) -> None:
        """
        Adds a new manager defined by manager_instructions (in dataclass format) to the current configuration.

        It is the caller's responsibility to ensure that manager_instructions are in the correct format.
        TODO: Change format if needed?

        We assume that the current configuration was already set up correctly.

        So this function just
        - adds the manager_instruction (so we can get an updated JSON)
        - run's add-manager hooks
        - ensures that data_source_order remains a permutation
        """
        # Note: self.data_source_descriptions is computed on demand. Need to access it before adding manager.
        descriptions = self.data_source_descriptions
        data_source_order = self.data_source_order

        # TODO: Output ordering
        new_manager: BaseCVManager = self._create_manager_from_instruction(manager_instruction)
        self._managers.append(new_manager)
        self._python_recipe.managers.append(manager_instruction)
        self._json_recipe = None  # force re-computation
        new_manager.post_setup(create=CreateManagerEnum.add_manager)
        new_data_sources = new_manager.data_source_descriptions
        for new_data_source in new_data_sources:
            new_index = len(data_source_order)
            position_type = new_data_source.position_type
            priority = new_data_source.priority
            for i in range(new_index):
                cmp_desc = descriptions[data_source_order[i]]
                if (cmp_desc.position_type > position_type) or ((priority is not None) and (cmp_desc.position_type == position_type) and (cmp_desc.priority is None or cmp_desc.priority > priority)):
                    data_source_order.insert(i, new_index)
                    break
            else:
                data_source_order.append(new_index)
            descriptions.append(new_data_source)
        # TODO: Other orderings
        assert data_source_order is self.data_source_order
        assert descriptions is self.data_source_descriptions
        while self.post_process_setup:
            self.post_process_setup.popleft()()
        # TODO: Notify other managers?
        self._re_init(setup_managers=True)

    def _find_manager(self, manager_identifier: Union[BaseCVManager, int], /) -> Tuple[int, BaseCVManager]:
        """
        Given either the index of the given manager in self.managers (by identity) or the manager itself, returns both.
        """
        if isinstance(manager_identifier, int):
            return manager_identifier, self.managers[manager_identifier],
        assert isinstance(manager_identifier, BaseCVManager)
        for i in range(len(managers := self.managers)):  # accessing self.managers ensures setup
            if managers[i] is manager_identifier:
                return i, manager_identifier
        raise ValueError("manager not found in this config")

    def remove_manager(self, manager_identifier: Union[BaseCVManager, int], /) -> None:
        """
        Removes the selected manager (given as either an index or the manager itself within (by identity) self.managers)
        """
        manager_pos, manager = self._find_manager(manager_identifier)

        data_source_descriptions = self.data_source_descriptions  # To force computing them before calling delete_manager()
        source_descriptions_left_to_remove: int = len(manager.data_source_descriptions)
        manager.delete_manager()
        assert self.python_recipe.managers[manager_pos] is manager.instructions
        del self.python_recipe.managers[manager_pos]
        # Remove all data_source_descriptions with this manager:
        i = 0
        while i < len(self.data_source_order):
            j = self.data_source_order[i]
            if data_source_descriptions[j].manager is manager:  # Remove i -> j
                for t in range(len(self.data_source_order)):
                    if self.data_source_order[t] > j:
                        self.data_source_order[t] -= 1
                del self.data_source_order[i]
                del data_source_descriptions[j]
                source_descriptions_left_to_remove -= 1
            else:
                i += 1
        assert source_descriptions_left_to_remove == 0
        # TODO: Notify managers?
        self._json_recipe = None
        self._re_init(setup_managers=True)

    def change_manager(self, manager_identifier: Union[BaseCVManager, int], new_instruction: ManagerInstructions, /) -> None:
        manager_pos, manager = self._find_manager(manager_identifier)
        manager.change_instruction(new_instruction, self._python_recipe)  # Note: This might change self.py_python_recipe
        self._json_recipe = None
        self._python_recipe.managers[manager_pos] = new_instruction
        self._re_init(setup_managers=True)

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
    def register(cls, /, type_id: str, creator: Callable, *, allow_overwrite: bool = False) -> None:
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

