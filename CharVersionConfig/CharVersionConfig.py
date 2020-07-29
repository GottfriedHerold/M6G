from __future__ import annotations
import json
import logging
import warnings
from importlib import import_module
from typing import ClassVar, Dict, Callable, TYPE_CHECKING, Optional, List, Deque, Literal, ValuesView, Final
from collections import deque
from CharGenNG.conditional_log import conditional_log
import copy

from django.db import transaction

from .EditModes import EditModes
from .types import validate_strict_JSON_serializability, PythonConfigRecipe, ManagerInstructionGroups, CreateManagerEnum, ManagerInstruction, UUID, UUID_to_JSONable_recursive

if TYPE_CHECKING:
    from CharData.BaseCharVersion import BaseCharVersion
    from DataSources import CharDataSourceBase
    from DBInterface.models import CharVersionModel
    from .BaseCVManager import BaseCVManager
    from .DataSourceDescription import DataSourceDescription
    from .types import PythonConfigRecipe_SerializedDict


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
    Ordering of data sources (The managers define a *dict* of data sources, but this is then re-ordered)
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
    # (typically, the callable is the subclass of the manager)
    # To fill this dict, callables need to register with CVConfig. This is done automatically upon import when
    # subclassing from BaseCVManager via a __init_subclass__ hook.
    known_types: ClassVar[Dict[str, Callable[..., BaseCVManager]]] = {}  # stores known type-identifiers and their callable.

    _python_recipe: PythonConfigRecipe
    _json_recipe: Optional[str]

    _edit_mode: EditModes  # enum type
    _managers: Optional[Dict[UUID, BaseCVManager]]
    _char_version: Optional[BaseCharVersion]  # weak-ref?
    _db_char_version: Optional[CharVersionModel]  # weak-ref?

    post_process_setup: Deque[Callable[[], None]]
    post_process_make_data_sources: Deque[Callable[[list], list]]
    post_process_validate: Deque[Callable[[], None]]

    #  No longer needed
    #  post_process_copy_config: Deque[Callable[[PythonConfigRecipe], None]]  # Not setup in init!

    _data_source_descriptions: Optional[Dict[UUID, DataSourceDescription]]
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
        is initially attached to. We infer db_char_version from char_version if char_version is attached to a DB object.

        db_char_version (inferred or not) is stored as a reference, not as a copy. It is assumed that during the lifetime
        of a CharVersionConfig object, this referred db_char_version is always in sync with the database. Changing
        db_char_version at the call site (unless going through the CVConfig interface)
        will typically requring creating a new CVConfig, as the config needs reloading.

        For testing purposes, CVConfig does not require an associated char_version / db_char_version, but some
        functionalities and certain types of managers will not work.
        """
        # Checked in _make_clean. Note that we might infer from_json from db_char_version.
        # if (from_python is None) == (from_json is None):
        #    raise ValueError("Exactly one of from_python= or from_json= must be given and not be None.")
        if from_python:
            from_python = copy.deepcopy(from_python)
        self._make_clean(from_python=from_python, from_json=from_json,
                         char_version=char_version, db_char_version=db_char_version)
        if validate_syntax:
            self.validate_syntax(self._python_recipe)
        if setup_managers:
            self.setup_managers(create=CreateManagerEnum.no_create)
        if validate_setup:
            self.validate_setup()

    @classmethod
    def create_char_version_config(cls, *, from_python: PythonConfigRecipe = None, from_json: str = None,
                                   char_version: BaseCharVersion = None, db_char_version: CharVersionModel = None,
                                   setup_managers: Literal[True], db_write_back: Literal[False]) -> CVConfig:
        """
        Called upon creating a new char in the database, returns a new char_version_config for this.

        Note that the difference to calling CVConfig(...) is that CVConfig provides an interface to a Config / db entry
        which is serialized in the database, whereas create_char_version_config is used when creating it.
        It calls on-create hooks on the managers, which may touch the database. Create_char_version_config itself
        does NOT touch the database.

        This should be called EXACTLY ONCE for a given (db version of) char_version config and the result saved in the db.

        Note that uuids and reference validity need to be correct before calling this function. The on-create hooks
        are ill-suited to fix / change the config in that regard; The purpose of this function is really only preparing
        db entries. If fixing references is requires, add the relevant managers.

        The db_char_version entry must already exist in the db (but can be a minimal / semantically invalid entry) and
        its config entry will have to be overwritten using the result of this call within the same db transaction.
        This is because managers may need the database primary key to create db references upon setup.
        """
        # TODO: Reconsider forcing db_write_back == False.
        assert not db_write_back
        assert setup_managers  # for now. Create_char_version_config always runs setup, essentially just to run checks.
        if transaction.get_autocommit():  # Essentially always a bug. Note that django.test.TestCase wraps everything.
            config_logger.critical("Calling create_char_version_config outside a transaction")
            warnings.warn("create_char_version_config should be wrapped in a transaction.", RuntimeWarning)
        # NOTE: the cls constructor stores a (deep!)copy of from_python, if set
        new_char_version_config = cls(from_python=from_python, from_json=from_json,
                                      char_version=char_version, db_char_version=db_char_version,
                                      setup_managers=False, validate_setup=False,
                                      validate_syntax=True)
        if new_char_version_config.db_char_version is None:  # This case makes little sense outside of specific testing instances.
            conditional_log(config_logger, 'Called create_char_version_config without and associated db entry', normal_level='critical', test_level='info')
        new_char_version_config.setup_managers(create=CreateManagerEnum.create_config)
        new_char_version_config._re_init(setup_managers=setup_managers)
        return new_char_version_config

    def destroy_char_version_config(self, db_write_back: Literal[False]) -> None:
        """
        Needs to be run before the char version (config) is deleted from the database. This informs managers
        that they should do some cleanup (typically nothing is required, as the DB will do the cleanup);
        this function pairs with create_char_version_config.
        Note that we do NOT call the individual managers' removal-from-config hooks.
        """
        assert not db_write_back
        if transaction.get_autocommit():  # Essentially always a bug. Note that django.test.TestCase wraps everything.
            config_logger.critical("Calling destroy_char_version_config outside a transaction")
            warnings.warn("destroy_char_version_config should be wrapped in a transaction.", RuntimeWarning)
        if self.db_char_version is None:  # This makes little sense outside of specific testing instances.
            conditional_log(config_logger, 'Called destroy_char_version_config without an associated db entry', normal_level='critical', test_level='info')
        self._re_init(setup_managers=False)  # Note that this validates the syntax before deletion.
        self.setup_managers(create=CreateManagerEnum.destroy_config)

    def _re_init(self, *, setup_managers: bool) -> None:
        """
        Resets the cv_config into an initial state as if it was just created with the given parameters
        (with from_python=self.python_recipe)
        validations are always run if possible, as this is essentially only called whenever the config changes.

        Note: char_version and db_char_version have no default (because both None and "use old params" are meaningful).
        As this is an internal interface, we are explicit here.
        """
        if self.post_process_setup or self.post_process_validate or self.post_process_make_data_sources:
            # This can only happen if some manager hook writes into the post_process queue of a *different* hook.
            config_logger.critical("Post-process queue not empty when calling _re_init")
            warnings.warn("Post-process queue not empty", RuntimeWarning)
            # _make_clean clears the above post_process queues.
        self._make_clean(from_python=self.python_recipe, char_version=self._char_version, db_char_version=self._db_char_version)
        self.validate_syntax(self._python_recipe)
        if setup_managers:
            self.setup_managers(create=CreateManagerEnum.no_create)
            self.validate_setup()  # We always validate, since re-init is only ever called upon changing to a presumably valid config.

    def _make_clean(self, *, from_python: Optional[PythonConfigRecipe] = None, from_json: Optional[str] = None,
                    char_version: BaseCharVersion, db_char_version: CharVersionModel) -> None:
        """
        Puts the char_version in a valid pristine state, no matter what state it was in before.
        Managers are not setup yet, so the only usable feature is JSON <-> Python description serialization.
        (or setting up managers)

        Note that (as opposed to __init__) this function stores a reference to the mutable from_python argument, which
        may be mutated later. This is fine for internal use.
        :param char_version: char_version object (interface for actual data) associated. May be None and can be set later.
        :param db_char_version: char_version_model in DB that this config is associated with. May be None and can be set later.
        :param from_python: python configuration for the manager.
        :param from_json: JSON configuration for the manager.

        If db_char_version is None, we try to derive it from char_version, if possible.
        We disallow providing both from_json and from_python. If both are None, we get the config from the db_char_version.
        :return: None
        """
        if (from_python is not None) and (from_json is not None):
            raise ValueError("Do not provide both from_python= and from_json= be given and not be None.")
        self._associate_initial_char_version(char_version=char_version, db_char_version=db_char_version)
        if (from_python is None) and (from_json is None):
            if not self.has_db_char_version:
                raise ValueError("Need to give one of from_python or from_json or a database entry")
            from_json=self.db_char_version.json_config
        self._setup_recipe(from_python=from_python, from_json=from_json)
        self._setup_queues()
        self._clear_managed_data()

    def _setup_recipe(self, from_python: PythonConfigRecipe = None, from_json: str = None) -> None:
        """
        Sets up the recipe information contained in the char version, converting Python <- JSON.
        Exactly one of from_python or from_json must be given.
        Note: Stores mutating reference to mutable from_python, if given.
        """
        if from_json is not None:
            self._json_recipe = from_json
            _py_recipe_dict: PythonConfigRecipe_SerializedDict = json.loads(self._json_recipe)
            self._python_recipe = PythonConfigRecipe.from_serialized_dict(_py_recipe_dict)
            self._edit_mode = self._python_recipe.edit_mode
        else:
            assert from_python is not None
            self._python_recipe = from_python
            self._edit_mode = from_python.edit_mode
            self._json_recipe = None  # Created on demand

    def _associate_initial_char_version(self, char_version: BaseCharVersion = None, db_char_version: CharVersionModel = None) -> None:
        """
        Associates the given char_version and db_char_version to the given config.
        db_char_version is inferred from char_version, if possible.
        This function does not care about previous assignments, if any.

        Note that char_version and db_char_version are checked for compatibility if both are given.
        """
        self._char_version = char_version
        # infer db_char_version from char_version, if possible (and check that it is compatible with db_char_version)
        if char_version:
            self._db_char_version = char_version.db_instance
            if db_char_version and db_char_version != self._db_char_version:
                if self._db_char_version:
                    raise ValueError("Provided char_version's db version and directly provided db_char_version do not match")
                else:
                    # both char_version and db_char_version are not None, but char_version.db_instance is None.
                    # This is fishy, but we accept it, taking the explicit db_char_version.
                    # Maybe char_version.db_instance is set later...
                    config_logger.error("Providing both unassociated char_version and explicit db_char_version")
                    self._db_char_version = db_char_version  # would be done below anyway.
        else:
            self._db_char_version = None
        if not self._db_char_version:
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
        assert not self.setup_has_run  # Otherwise, we would need to call a hook on the managers.
        old_char_version = self._char_version
        old_db_char_version = self._db_char_version
        self._associate_initial_char_version(char_version=char_version, db_char_version=db_char_version)
        if (old_char_version and (old_char_version != self._char_version)) or (old_db_char_version and (old_db_char_version != self._db_char_version)):
            raise ValueError("associate_char_version called with char_version/db_char_version incompatible with previous association")

    def _setup_queues(self, /) -> None:
        """
        Initialized the post-process queues with empty deques. Called from _make_clean.
        """
        self.post_process_setup = deque()
        self.post_process_make_data_sources = deque()
        self.post_process_validate = deque()

    def _clear_managed_data(self, /) -> None:
        """
        Sets all (optional) data that is computed after setup on demand to its pristine state (i.e. to None).
        Called from _make_clean
        """
        self._managers = None
        self._data_source_descriptions = None
        self._data_sources = None

    @property
    def managers(self, /) -> ValuesView[BaseCVManager]:
        """
        Access the managers as a list. Note that we do not set up the managers on demand for now, but raise an exception
        if setup has not yet been run. Setting up the managers on demand should never be needed and indicates a bug.
        """
        if self._managers is None:
            raise ValueError("Need to setup managers first")
        return self._managers.values()

    def manager_by_uuid(self, uuid: UUID, /) -> BaseCVManager:
        return self._managers[uuid]

    @property
    def setup_has_run(self, /) -> bool:
        """
        Checks whether the managers have been setup. Note that if not, accessing self.managers raises an exception.
        Note that this is a property, not a method.
        """
        return self._managers is not None

    def setup_managers(self, /, create: CreateManagerEnum, **kwargs) -> None:
        """
        Sets up the list of managers. This needs to be called exactly once after setup to do anything useful.
        It creates the list of managers according to the recipe given by JSON / python dict using the callables
        registered with the Manager types.
        After that, we call post_setup on every managers (this is so that post_process can inspect *other* managers
        or data set by them), then the post_process_setup queue.

        the create parameter is used to inform the managers about conditions like set up for the first time for this config.
        The default corresponds to setting up a manager of a config that was serialized before as it is.
        """
        if self.setup_has_run:
            raise ValueError("Trying to set up managers multiple times")
        self._managers = {uuid: self._create_manager_from_instruction(manager_instruction) for uuid, manager_instruction in self.python_recipe.manager_instructions.items()}
        for manager in self.managers:
            manager.post_setup(create=create, **kwargs)
        while self.post_process_setup:
            self.post_process_setup.popleft()()

    @property
    def data_source_descriptions(self, /) -> ValuesView[DataSourceDescription]:
        """
        Gets an iterator (ValuesView) of the data source descriptions. Requires the managers to have been set up before.
        """
        if self._data_source_descriptions is None:
            # _setup_data_source_descriptions writes to _data_source_descriptions, so we only call this once.
            self._setup_data_source_descriptions()
        return self._data_source_descriptions.values()

    def data_source_description_by_uuid(self, uuid: UUID, /) -> DataSourceDescription:
        """
        Note that this requires self._setup_data_source_descriptions() being run beforehand.
        """
        return self._data_source_descriptions[uuid]

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
    def has_char_version(self, /) -> bool:
        return self._char_version is not None

    @property
    def db_char_version(self, /) -> CharVersionModel:
        """
        Gets the associated DB char version.
        Be wary of staleness of db_char_version.
        """
        if self._db_char_version is None:
            raise ValueError("No db entry associated to this config.")
        return self._db_char_version

    @property
    def has_db_char_version(self, /) -> bool:
        return self._db_char_version is not None

    def take_uuid(self, /) -> UUID:
        """
        Obtain a new (numerical) UUID for this char version.
        This function should only be called from associated managers for setting up their uuids.
        Note that calling it changes the config; we do not write back to the DB here, because every meaningful caller
        will use the result to make further changes to the config anyway.
        """
        self._json_recipe = None
        return self._python_recipe.take_uuid()

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
    def data_source_order(self, /) -> List[UUID]:
        """
        Gets the data source ordering. The result is a permutation of keys of self.data_source_descriptions.
        """
        return self.python_recipe.data_source_order

    def write_back_to_db(self, /) -> None:
        if transaction.get_autocommit():
            raise RuntimeError("writing to db only allowed inside a transaction.")
        # This should really do nothing.
        self.db_char_version.refresh_from_db()
        self._json_recipe = None
        self.db_char_version.json_config = self.json_recipe
        self.db_char_version.save()

    @property
    def edit_mode(self, /) -> EditModes:
        return self._edit_mode

    def _create_manager_from_instruction(self, manager_instruction: ManagerInstruction, /) -> BaseCVManager:
        """
        Creates a manager using the given instruction.
        Note that the created manager keeps a reference to the passed manager_instruction.
        """
        type_id = manager_instruction.type_id
        if type_id not in type(self).known_types:
            import_module(manager_instruction.module)
        # TODO: Type-Check that return type is correct?
        return type(self).known_types[type_id](*manager_instruction.args, **manager_instruction.kwargs, uuid=manager_instruction.uuid, uuid_refs=manager_instruction.uuid_refs, cv_config=self, manager_instruction=manager_instruction)

    # internal-use keyword arguments used in _create_manager_from_instructions. Note that group is only used for display.
    _INTERNAL_MANAGER_KWARGS: Final = {'uuid', 'uuid_refs', 'cv_config', 'manager_instruction'}

    def _setup_data_source_descriptions(self, /):
        """
        Sets up the dict of data source descriptions.
        Called automatically upon access of data_source_descriptions
        """
        if self._managers is None:
            # Setup automatically?
            raise ValueError("Need to setup managers first")
        assert self._data_source_descriptions is None
        self._data_source_descriptions = {}
        for manager in self.managers:
            self._data_source_descriptions.update(manager.data_source_descriptions)

    def _ensure_data_source_descriptions(self, /):
        if self._data_source_descriptions is None:
            self._setup_data_source_descriptions()

    def _make_data_sources(self, /) -> None:
        """
        Creates the lists of data_sources and stores them in self._data_sources.
        Requires that setup_managers has been run.
        Data sources are created by querying data_source_descriptions.
        The order in which these are queried is determined by data_source_order, which is a list of keys in
        data_source_descriptions (We maintain the invariant that it
        is a permutation of all keys, although this is not really needed here). Each data_source_description
        in turns calls its related manager. (This roundabout way is because ordering data sources has nothing
        to do with ordering managers, a single manager can be responsible for several data source descriptions
        that need individual ordering and a single data source description actually encodes an arbitrary number
        (quite possibly 0) of data sources.
        """
        assert self._data_sources is None
        self._ensure_data_source_descriptions()
        self._data_sources: list = list()
        for data_source_description_index in self.data_source_order:
            # Note: We use .make_and_append_to because we do not want to specify whether a given data source desc refers
            # to a single data source or a quite possibly empty list.
            self.data_source_description_by_uuid(data_source_description_index).make_and_append_to(target_list=self._data_sources)
        while self.post_process_make_data_sources:
            self._data_sources = self.post_process_make_data_sources.popleft()(self._data_sources)

    @property
    def data_sources(self, /) -> List[CharDataSourceBase]:
        """
        Gets the data sources defined by the current config.

        These are created using the managers: Each manager defines a dict of data source (descriptions)
        and we use self._data_source_order to correctly order them.
        """
        if self._data_sources is None:
            self._make_data_sources()
        return self._data_sources

    def validate_setup(self, /) -> None:
        """
        Run every managers validation method (which can access the full config).
        Intended to be run directly after setup_managers()
        Indicates Errors by raising ValueError
        """
        try:  # catch and re-raise for logging.
            for manager in self.managers:  # Raises an exception if setup_managers() has run yet.
                manager.validate_config()
            self._ensure_data_source_descriptions()
            manager_uuid_set = set(self._managers.keys())
            dsd_uuid_set = set(self._data_source_descriptions.keys())
            if not manager_uuid_set.isdisjoint(dsd_uuid_set):
                raise ValueError("UUIDs of data source descriptions and managers not disjoint")
            for manager_uuid in manager_uuid_set:
                if manager_uuid != self.manager_by_uuid(manager_uuid).uuid:
                    raise ValueError("manager is wrong about its own uuid")
            for data_source_description_uuid in dsd_uuid_set:
                if data_source_description_uuid != self.data_source_description_by_uuid(data_source_description_uuid).uuid:
                    raise ValueError("data source description is wrong about its own uuid")
            while self.post_process_validate:
                self.post_process_validate.popleft()()
            if set(self.data_source_order) != dsd_uuid_set:
                raise ValueError("data_source_order is not a permutation of data_source_descriptions")
            # This takes care of duplicates: .keys() are guaranteed to be distinct, so checking length suffices.
            # Note that we MIGHT actually consider allowing duplicates.
            if len(self.data_source_order) != len(dsd_uuid_set):
                raise ValueError("data_source_order has contains duplicates")
        except Exception:
            # This also logs the exception.
            config_logger.exception("Validation of CVConfig failed")
            raise
        # TODO: Sortedness of data-source description according to group
        return

    def copy_config(self, *, target_db: Optional[CharVersionModel], new_edit_mode: Optional[EditModes], transplant: bool, db_write_back: Literal[False]) -> CVConfig:
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
        if not self.setup_has_run:
            raise ValueError("Source of copying must be setup")
        self._ensure_data_source_descriptions()
        assert not db_write_back
        if (target_db is not None) and transaction.get_autocommit():
            raise warnings.warn("copy_config should be wrapped in a transaction.", RuntimeWarning)
        if new_edit_mode is None:
            new_edit_mode = self.edit_mode

        # Shallow copy suffices, because CVConfig copies its from_python argument anyway; this is just for edit_mode
        new_py_recipe: PythonConfigRecipe = copy.copy(self.python_recipe)
        new_py_recipe.edit_mode = new_edit_mode

        new_config = CVConfig(from_python=new_py_recipe, db_char_version=target_db, validate_syntax=True, setup_managers=False)
        new_config.setup_managers(create=CreateManagerEnum.copy_config, transplant=transplant, old_config=self)
        new_config._json_recipe = None
        new_config._re_init(setup_managers=True)
        return new_config

        # self.post_process_copy_config = deque()
        # for manager in self.managers:
        #     manager.copy_config(new_py_recipe, transplant=transplant, target_db=target_db)
        # while self.post_process_copy_config:
        #     self.post_process_copy_config.popleft()(new_py_recipe)
        # new_config = CVConfig(from_python=new_py_recipe, validate_syntax=True, setup_managers=True)
        # new_config.validate_setup()
        # return new_config

    def add_manager(self, manager_instruction: ManagerInstruction, /, db_write_back: bool = False) -> None:
        """
        Adds a new manager defined by manager_instructions (in dataclass format, automatically deepcopied) to the current configuration.

        It is the caller's responsibility to ensure that manager_instructions are in the correct format, except
        that UUID is set automatically.

        We assume that the current configuration was already set up correctly.

        So this function just
        - adds the manager_instruction (so we can get an updated JSON)
        - run's add-manager hooks
        - ensures that data_source_order remains a permutation
        """
        # TODO: LaTeX output ordering

        # self.data_source_descriptions is computed on demand and a ValueView.
        # We need to access the raw value and ensure it was set up.
        self._ensure_data_source_descriptions()
        descriptions: Dict[UUID, DataSourceDescription] = self._data_source_descriptions
        data_source_order: List[UUID] = self.data_source_order
        manager_instruction = copy.deepcopy(manager_instruction)
        if manager_instruction.uuid is None:
            manager_instruction.uuid = self.take_uuid()
        new_uuid = manager_instruction.uuid
        if new_uuid in self._managers.keys():
            raise ValueError("Manager uuid is already present")

        # Add manager to python recipe:
        self._python_recipe.manager_instructions[new_uuid] = manager_instruction
        new_manager: BaseCVManager = self._create_manager_from_instruction(manager_instruction)
        self._managers[new_uuid] = new_manager
        self._json_recipe = None  # force re-computation

        # Run setup hooks on manager. Note that this may change the manager_instruction and the config.
        new_manager.post_setup(create=CreateManagerEnum.add_manager)

        # Fix data source order
        new_data_source_descriptions: Dict[UUID, DataSourceDescription] = new_manager.data_source_descriptions
        for new_data_source_description in new_data_source_descriptions.values():
            pos_in_ordering = self._find_new_data_source_description_insertion_position(new_data_source_description)
            new_desc_uuid = new_data_source_description.uuid
            if new_desc_uuid in descriptions:
                raise ValueError("Data source description's uuid is already present")
            data_source_order.insert(pos_in_ordering, new_desc_uuid)
            descriptions[new_desc_uuid] = new_data_source_description

        # Cleanup
        assert data_source_order is self.data_source_order
        assert descriptions is self._data_source_descriptions
        while self.post_process_setup:
            self.post_process_setup.popleft()()
        # TODO: Notify other managers?
        self._re_init(setup_managers=True)
        if db_write_back:
            self.write_back_to_db()

    # TODO: Add a cmp_key function to DataSourceDescription instead
    def _find_new_data_source_description_insertion_position(self, data_source_desc: DataSourceDescription, /) -> int:
        position_type = data_source_desc.position_type
        priority = data_source_desc.priority
        data_source_order: List[UUID] = self.data_source_order
        for i in range(len(data_source_order)):
            cmp_desc = self.data_source_description_by_uuid(data_source_order[i])
            if (cmp_desc.position_type > position_type) or (
                    (priority is not None) and (cmp_desc.position_type == position_type) and (
                    cmp_desc.priority is None or cmp_desc.priority > priority)):
                return i
        return len(data_source_order)

    def remove_manager(self, manager_uuid: UUID, /, db_write_back: bool = False) -> None:
        """
        Removes the selected manager (given as either an index or the manager itself within (by identity) self.managers)
        """
        manager = self.manager_by_uuid(manager_uuid)
        self._ensure_data_source_descriptions()

        # Call hook on manager. This is intentionally done before we remove anything from the config.
        manager.delete_manager()

        # Delete the affected components from the config. Note that self.data_source_descriptions is not modified,
        # as this is not stored in the python config anyway, and we recreate the config from the stored python recipe.
        self.python_recipe.data_source_order = list(filter(lambda uuid: self.data_source_description_by_uuid(uuid).manager is not manager, self.python_recipe.data_source_order))
        del self.python_recipe.manager_instructions[manager_uuid]
        # TODO: Notify other managers?
        self._json_recipe = None
        self._re_init(setup_managers=True)
        if db_write_back:
            self.write_back_to_db()

    def change_manager(self, manager_uuid: UUID, new_instruction: ManagerInstruction, /, db_write_back: bool) -> None:
        """
        Changes the instructions for a manager with the given uuid to a copy of the given new_instruction.
        Should be used to change parameters without affecting orderings etc.
        new_instruction.uuid must be None or match the managers.
        """
        manager = self.manager_by_uuid(manager_uuid)
        new_instruction = copy.deepcopy(new_instruction)
        if new_instruction.uuid is None:
            new_instruction.uuid = manager_uuid
        if new_instruction.uuid != manager_uuid:
            raise ValueError("new_instruction's uuid does not match manager's")
        self._json_recipe = None
        # Note: This changes self.py_python_recipe; actually updating the python_recipe and making changes to data source order etc. is the responsibility
        # of manager.change_instructions.
        manager.change_instruction(new_instruction, self._python_recipe)
        # self._python_recipe.manager_instructions[manager_uuid] = new_instruction
        self._re_init(setup_managers=True)
        if db_write_back:
            self.write_back_to_db()

    @classmethod
    def validate_syntax(cls, py: PythonConfigRecipe, /) -> None:
        """
        (Type-)Checks whether the python recipe has the correct form. Indicates failure by raising an exception.
        """
        if type(py) is not PythonConfigRecipe:
            raise ValueError("Invalid CVConfig: Wrong type")
        if type(py.edit_mode) is not EditModes:
            raise ValueError("Invalid CVConfig: Invalid edit mode")
        if type(py.manager_instructions) is not dict:
            raise ValueError("Invalid CVConfig: manager_instructions not dict")
        for manager_uuid, manager_instruction in py.manager_instructions.items():
            if type(manager_uuid) is not UUID:
                raise ValueError("Invalid CVConfig: manager instructions dict has non-UUID key")
            if manager_uuid != manager_instruction.uuid:
                raise ValueError("Invalid CVConfig: manager instructions' uuid does not match key")
            if type(manager_instruction.args) is not list:
                raise ValueError("Invalid CVConfig: args of manager instruction is not list")
            validate_strict_JSON_serializability(manager_instruction.args)
            validate_strict_JSON_serializability(UUID_to_JSONable_recursive(manager_instruction.uuid_refs))
            kwargs = manager_instruction.kwargs
            if type(kwargs) is not dict:
                raise ValueError("Invalid CVConfig: kwargs of manager instructions is not dict")
            validate_strict_JSON_serializability(kwargs)
            if not cls._INTERNAL_MANAGER_KWARGS.isdisjoint(kwargs.keys()):
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
            if type(entry) is not UUID:
                raise ValueError("Invalid CVConfig: data_source_order is not list of UUIDS")
        if len(py.data_source_order) != len(set(py.data_source_order)):
            raise ValueError("Invalid CVConfig: data_source_order contains duplicates.")

    @classmethod
    def register(cls, /, type_id: str, creator: Callable, *, allow_overwrite: bool = False) -> None:
        """
        Registers the callable (typically a class) creator with the given type_id. This then makes it possible to
        use this string as a type in recipes to create managers using the given creator.
        You need to set allow_overwrite=True to allow re-registering a given type_id with a new, different creator.
        """
        if type_id in cls.known_types:
            if cls.known_types[type_id] == creator:
                config_logger.info("Re-registering CVManager %s with same creator" % type_id)
                return
            elif allow_overwrite:
                config_logger.info("Re-registering CVManager %s with new creator, as requested" % type_id)
            else:
                config_logger.critical("Trying to re-register CVManager %s with new creator, failing." % type_id)
                raise ValueError("Type identifier %s is already registered with a different creator" % type_id)
        cls.known_types[type_id] = creator
        config_logger.info("Registered CV %s" % type_id)
