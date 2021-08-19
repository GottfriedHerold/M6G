"""
TODO: Redo lookup specification!!! THIS IS OUTDATED
This module defines a class that is used to hold and access a (version of a) character's data.
Note that characters are supposed to be versioned in a simple (non-branching) fashion.
The main data that is used to hold the character is a list S = [S0,S1,S2,...] of dict-like data source objects.
Its keys are PATHS of the form e.g. 'att.st', 'abil.zauberkunde.gfp_spent' (all lowercase, separated by dots)
When looking up e.g. 'abil.zauberkunde.gfp_spent', we actually look for a value in this order:
first, look up S0[abil.zauberkunde.gfp_spent], then S1[abil.zauberkunde.gfp_spent], ...
then  S0[abil.zauberkunde._all], S1[abil.zauberkunde._all], ...
then  S0[abil.gfp_spent], S1[abil.gfp_spent], ...
then  S0[abil._all], S1[abil._all], ...
then  S0[gfp_spent], S1[gfp_spent], ...
finally S0[_all], S1[_all], ...
We take the first match we find and return an arbitrary python object.

The BaseCharVersion class itself only takes care about managing these dict-like data sources and the lookup.
To actually use it, you will probably have to subclass it and override/add some @property-methods to tie
a CharVersion's metadata not contained in self.lists such as last_change to a database.

The individual data sources need to satisfy a certain interface. Derive from CharDataSourceBase to satisfy it.
Note that BaseCharVersion does not copy its data sources. While a BaseCharVersion object holds a data source in its lists,
do not edit the data source object directly, but through methods provided by BaseCharVersion.
(This is because BaseCharVersion might introduce caching in the future)
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional, Union, Any, Tuple, Generator, Iterable, Callable, TypeVar, Dict, Iterator, Final, TYPE_CHECKING, ClassVar
from functools import wraps
import itertools

from . import Regexps
from . import Parser
from . import CharExceptions
from . import ListBuffer
from CharVersionConfig import CVConfig, PythonConfigRecipe
from DBInterface.models.meta import KEY_MAX_LENGTH

if TYPE_CHECKING:
    from DataSources import CharDataSourceBase
    from CharVersionConfig import ManagerInstruction, BaseCVManager

_Ret_Type = TypeVar("_Ret_Type")
_Arg_Type = TypeVar("_Arg_Type")

_ALL_SUFFIX: Final = "_all"

# Expressions to denote wildcards in lookup keys for the CEL.
# NOTE: _all can match 0 times. We do not allow multiple occurrences of _all in a single key.
# This is prevented upon creating such entries. Querying "_all" and "_any" explicitly is possible and can lead to lookup
# finding the same entry multiple times. Queries with multiple explicit occurrences of "_any" are possible in principle.
# Of course, they will only match via wildcard expansion.
_WILDCARD_ONE: Final = "_any"  # corresponds to "?" (match single)
_WILDCARD_ANY: Final = "_all"  # corresponds to "*" (match arbitrary number of sub-keys)


# TODO: Derive from Other Exception(s):
#  Candidates are django's PermissionDenied (To make django return the correct http error to the user)
#  or CharData.CharExceptions.CharGenException.
class CharPermissionError(Exception):
    pass


class NoWritePermissionError(CharPermissionError):
    pass


# This may be raised from __init__ in a subclass. Included here for consistency.
class NoReadPermissionError(CharPermissionError):
    pass


class InvalidKeyError(Exception):
    pass

def valid_key(key: str) -> bool:
    """
    valid_key checks whether a supposed key (to out database defining properties of chars) satisfies some additional
    validity constraints. Note that we suppose that key matches re_key_any. This checks for further constraints that
    come from limitations of the language or the database.
    """
    match = Regexps.re_key_any.fullmatch(key)
    assert match
    if len(key) > KEY_MAX_LENGTH:
        return False
    split_key = key.split(".")
    wildcards = 0
    for part in split_key:
        if part == _WILDCARD_ANY:
            wildcards += 1
    return wildcards <= 1


def invert_key_at_wildcard(key: str) -> List[str]:
    """
    TODO:
    """
    assert Regexps.re_key_any.fullmatch(key)
    if len(key) > KEY_MAX_LENGTH:
        raise InvalidKeyError
    split_key = key.split(".")
    wildcard_pos = -1
    for i in range(len(split_key)):
        if split_key[i] == _WILDCARD_ANY:
            if wildcard_pos >= 0:
                raise InvalidKeyError
            wildcard_pos = i
    if wildcard_pos == -1:
        return []
    split_key[wildcard_pos:].reverse()
    return split_key


class BaseCharVersion:
    """
    This class models a version of a given character. It (or rather, some derived classes) also acts as the interface
    for the fronted <-> backend: all modifications / reads of a given character version must go through this interface.

    On a high level, a char version consists of
    -   some purely descriptive metadata (such as creation_time, timestamp of last edit, a custom description). These
        are exclusively used to let a user select the correct version.
    -   A list of dict-like data_sources (instances of classes derived from CharDataSourceBase).
        Each of those holds key-value pairs such as 'attr.strength': 79
        (data_sources may hold both parsed data such as 79 or the string '79' that the user actually input)
    -   metadata as an instance of the class CVConfig. This metadata is used, among other things, to define
        which data sources are actually present.

    BaseCharVersion only implements some basic interface to CVConfig, to CharDataSourceBase and to the descriptive metadata.
    Furthermore, it implements the complicated lookup logic that we use to select values from the data_sources and is responsible
    for providing an interface to the Chargen Expression Language that allows users to input formulas.

    Note that BaseCharVersion is supposed to be subclassed in order to add synchronization abilities with a database.
    BaseCharVersion itself is only used to simplify testing without requiring database management.

    Derived classes are supposed to be used in a with ... clause such that all operations go through a single database
    transaction.
    """

    # These attributes possibly exist in derived classes. They are included here in the base class for consistency and
    # to define __str__. The default implementation in the base class here also writes to last_changed.
    # If given as args to __init__ they are written to, otherwise, they are NOT set by __init__ at all!

    # Those attributes are overwritten by @property - objects in derived classes to tie to db.
    #
    # In derived classes, some of the property descriptors are non-trivial and/or read-only!
    # (Note that creation_time and name are read-only if tied to db and last_changed is managed by django/db)
    # The only attribute written to from the base class outside of __init__ (upon explicit request) to is last_changed;
    # all such writes go through _update_last_changed()
    creation_time: datetime  # only written to we creation_time is explicitly passed.
    last_changed: datetime  # updated at each change
    description: str = "nondescript"
    name: str
    version_name: str = "unnamed"

    db_instance: ClassVar = None  # overwritten in subclasses
    # db_write_back controls the write-back default argument of the configuration manipulation interface.
    # If set, functions such as cls.add_manager(...) will by default write their changes back to the db.
    db_write_back = False

    # mutating methods check write_permissions and raise an exception if not True.
    # We do not need read_permission attributes: If such a read_permission was not True, __init__ should instead
    # raise an exception: we cannot do anything with the BaseCharVersion anyway.
    # Changing permissions during the lifetime of a BaseCharVersion needs to go through a dedicated interface and is not supported at the moment.
    # Note that permissions are dropped in __init__, taking into account the edit_mode of the config, if given.
    data_write_permission: bool = True  # Overridden on an instance-by-instance basis and in derived classes.
    config_write_permission: bool = True  # Overridden on an instance-by-instance basis and in derived classes.

    # Internally used to speed up lookups, these are set in self._update_list_lookup_info:
    _unrestricted_lists: list = []  # indices of data sources that contain unrestricted keys in lookup order
    _restricted_lists: list = []  # indices of data sources that contain restricted keys in lookup order
    _type_lookup: dict = {}  # first index of data source for a given dict_type
    _desc_lookup: dict = {}  # first index of data source for a given description
    _default_target: Optional[int] = None  # index that writes go by default

    _config: Optional[CVConfig]  # TODO: May remove Optional if direct data_sources interface goes away.
    # Important: Access to members of _config needs to go through self.config, not self._config
    # because self.config is non-trivially overridden in subclasses.

    _data_sources: List[CharDataSourceBase]

    def __init__(self, *, data_sources: List[CharDataSourceBase] = None, config: CVConfig = None, py_config: PythonConfigRecipe = None, json_config: str = None,
                 data_write_permission: bool = None, config_write_permission: bool = None,
                 creation_time: datetime = None, last_changed: datetime = None, description: str = None, name: str = None, version_name: str = None):
        """
        Creates a BaseCharConfig. You should set either initial_list or config/py_config/json_config to initialize its lists (if config is set,
        it will use config to set up the lists). Note that config is the preferred way; the data_sources interface exists
        exclusively for debugging and testing purposes, may not be present in subclasses, and may be removed altogether.

        If config: CVConfig is used, config must NOT have run setup_managers() yet. This is done here in __init__.

        data_write_permissions and config_write_permission define the permissions for acting through this BaseCharVersion.
        Note that, if set and we have a config, they must be compatible with the edit_mode.
        If None, we use a default (taking edit_mode into account)

        Other keyword-only arguments (creation_time, last_changed, descriptionm name, version_name), if present,
        force writing to self. They are provided for compatibility with derived classes. (see above)
        """
        if (data_sources is None) + (config is None) + (py_config is None) + (json_config is None) != 3:
            raise ValueError("Need to provide exactly one of data_sources or some form of config")
        if data_sources is None:
            if py_config is not None:
                self._config = CVConfig(from_python=py_config, char_version=self, setup_managers=True)
            elif json_config is not None:
                self._config = CVConfig(from_json=json_config, char_version=self, setup_managers=True)
            else:
                self._config = config
                config.associate_char_version(char_version=self)
                self.config.setup_managers()  # TODO: Needs changes due to modifications of manager management
            # self._data_sources is set from self._updated_config()
        else:
            # TODO: Might go away completely.
            from django.conf import settings
            if not settings.TESTING_MODE:
                raise RuntimeWarning("data sources interface to CharData is deprecated")
            self._data_sources = data_sources
            self._config = None

        if data_write_permission is not None:
            self.data_write_permission = data_write_permission
        if config_write_permission is not None:
            self.config_write_permission = config_write_permission

        # TODO: if direct data source interface goes away, may simplify and remove if self._config
        if self._config:
            edit_mode = self.config.edit_mode
            if not edit_mode.may_edit_data():  # TODO: WAS NOT NOT. Sure?
                if data_write_permission:
                    raise ValueError("Explicitly set data_write_permissions incompatible with edit_mode")
                self.data_write_permission = False
            if not edit_mode.may_edit_config():
                if config_write_permission:
                    raise ValueError("Explicitly set config_write_permissions incompatible with edit_mode")
                self.config_write_permission = False

        # TODO: Might go away completely.
        if last_changed:
            self.last_changed = last_changed
        if creation_time:
            self.creation_time = creation_time
            self._update_last_changed()
        if description:
            self.description = description
            self._update_last_changed()
        if name:
            self.name = name
            self._update_last_changed()
        if version_name:
            self.version_name = version_name
            self._update_last_changed()
        self._updated_config()

    def __enter__(self):
        raise NotImplementedError

    def __exit__(self, exc_type, exc_val, exc_tb):
        raise NotImplementedError

    def _save(self):
        """
        Saves back to db. Implemented in derived classes.
        """
        raise NotImplementedError

    def _update_last_changed(self) -> None:
        """
        Updates self.last_changed to the current time.
        """
        self.last_changed = datetime.now(timezone.utc)

    @property
    def name(self, /) -> str:
        return getattr(self, '_name', self.version_name)

    @name.setter
    def name(self, value, /) -> None:
        self._name = value

    def __str__(self) -> str:
        return self.name

    class _Decorators:
        @staticmethod
        def act_on_data_source(action: Callable[..., _Ret_Type], /) -> Callable[..., _Ret_Type]:
            """
            Decorator that takes a BaseCharVersion method action(self, source, ...)
            and turns into a method action(self, ..., where=None, target_type=None, target_desc=None) with keyword-only
            parameters where, target_type, target_desc instead of source.
            The new action calls original action with source as the data source defined by where, target_type and target_desc.
            """

            @wraps(action)  # I do not know how to adjust the type hints for _inner
            def _inner(self: BaseCharVersion, *args, where: Union[int, None, CharDataSourceBase] = None,
                       target_type: Optional[str] = None, target_desc: Optional[str] = None, **kwargs) -> _Ret_Type:
                if where is None:
                    where = self.get_target_index(target_type, target_desc)
                if isinstance(where, int):
                    return action(self, self.data_sources[where], *args, **kwargs)
                else:
                    if where not in self.data_sources:
                        raise LookupError("Invalid data source: Not in this BaseCharVersion's data list.")
                    return action(self, where, *args, **kwargs)

            if 'source' in _inner.__annotations__:
                del _inner.__annotations__['source']
            _inner.__annotations__['where'] = 'Union[int, None, CharDataSourceBase]'
            _inner.__annotations__['target_type'] = Optional[str]
            _inner.__annotations__['target_desc'] = Optional[str]
            return _inner

        @staticmethod
        def requires_write_permission(method):
            @wraps(method)
            def wrapped_method(self: BaseCharVersion, *args, **kwargs):
                if not self.data_write_permission:
                    raise NoWritePermissionError
                return method(self, *args, **kwargs)
            return wrapped_method

        @staticmethod
        def requires_config_write_permission(method):
            @wraps(method)
            def wrapped_method(self: BaseCharVersion, *args, **kwargs):
                if not self.config_write_permission:
                    raise NoWritePermissionError
                return method(self, *args, **kwargs)

            return wrapped_method

    @_Decorators.requires_config_write_permission
    def add_manager(self, manager_instruction: ManagerInstruction, /, db_write_back: bool = None) -> None:
        if db_write_back is None:
            db_write_back = self.db_write_back
        self.config.add_manager(manager_instruction, db_write_back=db_write_back)
        self._updated_config()

    @_Decorators.requires_config_write_permission
    def remove_manager(self, manager_identifier: Union[BaseCVManager, int], /, db_write_back: bool = None) -> None:
        if db_write_back is None:
            db_write_back = self.db_write_back
        self.config.remove_manager(manager_identifier, db_write_back=db_write_back)
        self._updated_config()

    @_Decorators.requires_config_write_permission
    def change_manager(self, manager_identifier: Union[BaseCVManager, int], new_instruction: ManagerInstruction, /,
                       db_write_back: bool = None) -> None:
        if db_write_back is None:
            db_write_back = self.db_write_back
        self.config.change_manager(manager_identifier, new_instruction, db_write_back=db_write_back)
        self._updated_config()

    @property
    def data_sources(self) -> List[CharDataSourceBase]:
        return self._data_sources

    @data_sources.setter
    def data_sources(self, new_lists, /):
        """
        Should only be called from debug code, really. May be removed in the future.
        """
        if not self.config_write_permission:
            raise NoWritePermissionError
        self._data_sources = new_lists
        self._update_list_lookup_info()

    @property
    def config(self) -> Optional[CVConfig]:
        return self._config

    #  No setter for config. We basically would need to create a new object.

    def _updated_config(self):
        if self._config:  # TODO: Basically always true... This is just needed for the legacy interface of directly giving data sources. Will be removed.
            self._data_sources = self.config.data_sources
        self._update_list_lookup_info()

    def _update_list_lookup_info(self) -> None:
        """
        Called to update internal data related to lookup on the data sources.
        """
        self._unrestricted_lists = []
        self._restricted_lists = []
        self._type_lookup = {}
        self._desc_lookup = {}
        self._default_target = None

        for i in range(len(self.data_sources)):
            list_i: CharDataSourceBase = self.data_sources[i]
            if list_i.contains_restricted:
                self._restricted_lists += [i]
            if list_i.contains_unrestricted:
                self._unrestricted_lists += [i]
            if list_i.dict_type not in self._type_lookup:
                self._type_lookup[list_i.dict_type] = i  # same as dict.setdefault below, but we have an ...else branch.
            elif list_i.type_unique:
                raise RuntimeError("Can only put one DataSource of type " + list_i.dict_type + " into CharVersion")
            self._desc_lookup.setdefault(list_i.description, i)
            if list_i.default_write:
                self._default_target = i

    # Some get/set functions require specifying a data source. This can be specified either by the where argument
    # (an integer as index into the list of data sources OR a data source itself) or by target_type and/or target_desc.
    # if no such argument is given at all, we fall back to a default data source, if one is marked as such.
    # target_type / target_desc must only be used if where is not used

    # Note the distinction between key and query: queries are what undergo our lookup rules. Keys are where lookup ends
    # up and are where things are stored under.

    def get_target_index(self, target_type: Optional[str], target_desc: Optional[str]) -> Optional[int]:
        """
        finds the index of a data source from target_type / target_desc. Mostly used internally.
        """
        if target_type is None:
            if target_desc is None:
                return self._default_target
            else:
                return self._desc_lookup[target_desc]
        else:
            if target_desc is None:
                return self._type_lookup[target_type]
            else:
                return next(filter(lambda data_source: data_source.dict_type == target_type and data_source.description == target_desc, self.data_sources), None)

    def _get_index_from_list(self, source: CharDataSourceBase, /) -> int:
        """
        Obtains i from source==self.lists[i]  (Note: We assume identity, not just equality)
        We assume that there are no duplicates, but if there were, returns the smallest index i s.t. self.lists[i] is source)
        Raises IndexError if source is not in self.lists
        """
        try:
            return next(filter(lambda i: self.data_sources[i] is source, range(len(self.data_sources))))
        except StopIteration:
            raise IndexError("Data source not contained in CharVersion")

    # IMPORTANT: @act_on_data_source changes the function signature!
    # These functions have keyword-only arguments where, target_type, target_desc rather than source.

    if TYPE_CHECKING:
        def get_data_source(self, *, where: Union[CharDataSourceBase, int, None] = None, target_type: Optional[str] = None, target_desc: Optional[str] = None) -> CharDataSourceBase: ...
    else:
        @_Decorators.act_on_data_source
        def get_data_source(self, source: CharDataSourceBase) -> CharDataSourceBase:
            return source

    if TYPE_CHECKING:
        def set(self, key: str, value: object, *, where: Union[CharDataSourceBase, int, None] = None, target_type: Optional[str] = None, target_desc: Optional[str] = None) -> None: ...
    else:
        @_Decorators.act_on_data_source
        @_Decorators.requires_write_permission
        def set(self, source: CharDataSourceBase, key: str, value: object) -> None:
            source[key] = value
            self._update_last_changed()

    if TYPE_CHECKING:
        def bulk_set(self, key_values: Dict[str, object], *, where: Union[CharDataSourceBase, int, None] = None, target_type: Optional[str] = None, target_desc: Optional[str] = None) -> None: ...
    else:
        @_Decorators.act_on_data_source
        @_Decorators.requires_write_permission
        def bulk_set(self, source: CharDataSourceBase, key_values: Dict[str, object]) -> None:
            source.bulk_set_items(key_values)
            if key_values:
                self._update_last_changed()

    if TYPE_CHECKING:
        def set_input(self, key: str, value: str, *, where: Union[CharDataSourceBase, int, None] = None, target_type: Optional[str] = None, target_desc: Optional[str] = None) -> None: ...
    else:
        @_Decorators.act_on_data_source
        @_Decorators.requires_write_permission
        def set_input(self, source: CharDataSourceBase, key: str, value: str) -> None:
            source.set_input(key, value)
            self._update_last_changed()

    if TYPE_CHECKING:
        def bulk_set_input(self, key_values: Dict[str, str], *, where: Union[CharDataSourceBase, int, None] = None, target_type: Optional[str] = None, target_desc: Optional[str] = None) -> None: ...
    else:
        @_Decorators.act_on_data_source
        @_Decorators.requires_write_permission
        def bulk_set_input(self, source: CharDataSourceBase, key_values: Dict[str, str]) -> None:
            source.bulk_set_inputs(key_values)
            if key_values:
                self._update_last_changed()

    if TYPE_CHECKING:
        def delete(self, key: str, *, where: Union[CharDataSourceBase, int, None] = None, target_type: Optional[str] = None, target_desc: Optional[str] = None) -> None: ...
    else:
        @_Decorators.act_on_data_source
        @_Decorators.requires_write_permission
        def delete(self, source: CharDataSourceBase, key: str) -> None:
            """
            Deletes data_source[key] where data_source is specified by where / target_type / target_desc.
            Trying to deleting keys that do not exist in the data_source may trigger an exception, as per Python's default.
            """
            del source[key]
            self._update_last_changed()

    if TYPE_CHECKING:
        def bulk_delete(self, keys: Iterable[str], *, where: Union[CharDataSourceBase, int, None] = None, target_type: Optional[str] = None, target_desc: Optional[str] = None) -> None: ...
    else:
        @_Decorators.act_on_data_source
        @_Decorators.requires_write_permission
        def bulk_delete(self, source: CharDataSourceBase, keys: Iterable[str]) -> None:
            source.bulk_del_items(keys)
            if keys:
                self._update_last_changed()

    if TYPE_CHECKING:
        def get_input(self, key: str, default: str, *, where: Union[CharDataSourceBase, int, None] = None, target_type: Optional[str] = None, target_desc: Optional[str] = None) -> str: ...
    else:
        @_Decorators.act_on_data_source
        def get_input(self, source: CharDataSourceBase, key: str, default: str = "") -> str:
            """
            Gets the input string that was used to set data_source[key] in the data_source specified by where / target_type / target_desc.

            Note about data_source behaviour:
            If data_source supports input_lookup, but key is not present, this returns default (empty string unless specified).
            If data_source does not support input_lookup, we return either None or some information string.
            We do NOT raise an exception.

            See also get_input_source for a version that determines data_source from the key.
            """
            return source.get_input(key, default=default)

    if TYPE_CHECKING:
        def bulk_get_inputs(self, keys: Iterable[str], default: str = "", *, where: Union[CharDataSourceBase, int, None] = None, target_type: Optional[str] = None, target_desc: Optional[str] = None) -> Dict[str, str]: ...
    else:
        @_Decorators.act_on_data_source
        def bulk_get_inputs(self, source: CharDataSourceBase, keys: Iterable[str], default: str = "") -> Dict[str, str]:
            return source.bulk_get_inputs(keys, default=default)

    def find_query(self, query: str, *, indices: Optional[Iterable[int]] = None) -> Tuple[str, int]:
        """
        Find where a given (non-function) query string is located in self.lists
        :param query: query string
        :param indices: None or list of indices to restrict lookup rules to
        :return: pair (query, index) such that self.lists[index][query] is where the lookup for key ends up
        """
        try:
            return next(self.find_lookup(query, indices=indices))
        except StopIteration:
            raise LookupError

    def get_input_source(self, query: str, *, default=("", True)) -> Tuple[str, bool]:
        """
        Retrieves the input source string for a given query string key as first return value.
        The second return value indicates whether the data source where lookup ends up has input data at all.
        Note: If the lookup ends in an actual data source that has input data, the returned input string cannot be "".

        If the query string is not found, returns default value, which is ("", True) if not given.
        (This default both unambiguously indicates "not found" and is also what we want to treat this case as-if in some
        contexts)

        If the second return value is False, the first may be None or an arbitrary string.
        """
        try:
            query, where = self.find_query(query)
        except LookupError:
            return default
        # Note that get_input should not throw an exception when stores_input_data is False,
        # but rather return some value indicating error (None, "", or an error message string)
        return self.get_input(query, where=where), self.data_sources[where].stores_input_data

    def bulk_get_input_sources(self, queries: Iterable[str], *, default=("", True)) -> Dict[str, Tuple[str, bool]]:
        return {query: self.get_input_source(query, default=default) for query in queries}

    def bulk_get(self, queries: Iterable[str], default=None) -> Dict[str, Any]:
        return {query: self.get(query, default=default) for query in queries}

    def get(self, query: str, *, locator: Iterable = None, default=None) -> Any:
        """
        Obtain an element from the current BaseCharVersion database by query name.

        locator should usually be None. It encodes the list or a generator of all results that match the query
        name according to our lookup rules. This is overridden to implement $AUTO(QUERY) calls.

        :param query: The key to query for.
        :param locator: iterable to implement lookup. Used to implement $Auto and function lookup from the parser.
        :param default: Default value returned if query is not found. If default is None, returns an error.
                        (in the form of a DataError object, not by raising an exception)
        :return: database entry or DataError (as return type, not raised) if key is not found.
        """
        if locator is None:
            # print('Calling with ' + query + ' empty locator')
            # This creates a generator that yields all matches for the query key according to our lookup rules.
            locator = self.find_lookup(query)
        # else:
            # print('Calling with ' + query + ' locator= ' + str(locator))

        # Note: We have to take care about modifications to locator.
        #
        # The issue is the following: Normally, we just need to take the first output from iterator. Call the
        # rest of the iterator its tail.
        # However, if this output is an AST like parse('$AUTO + $AUTO'), evaluation of that will recursively call
        # get with iterator set to the tail, TWICE. We cannot guarantee that arbitrary iterables support being iterated
        # over twice (lists support that, generator expressions don't). In general, iteration mutates the iterable.
        # We could copy tail into a list, but iterating locator is generally very expensive, so we only wish to do that
        # if needed.
        # For that reason, we copy the tail into a ListBuffer.LazyIterList object that wraps locator into a buffered
        # iterable/iterator that supports multiple independent iterators and pass it to the AST evaluation.

        locator_iterator = iter(locator)  # If locator is a ListBuffer.LazyIterList, this actually creates a copy.
        # This copying is actually not necessary, but works.

        try:
            # where is the index of the list where we found the match, located_key is the key within that list.
            # Often, located_key == query, but located_key may be the fallback key that was actually found according
            # to the lookup rules.
            located_key, where = next(locator_iterator)
        except StopIteration:
            if default is None:
                return CharExceptions.DataError(query + " not found")
            return default

        ret = self.data_sources[where][located_key]

        # If ret is an AST, we need to evaluate it (otherwise, we return the result directly). Note that string literals
        # without = are stored directly, not as ASTs.
        if isinstance(ret, Parser.AST):
            needs_env = ret.needs_env  # TODO: We may drop needs_env completely
            context = {'Name': located_key,
                       'Query': query,
                       Parser.CONTINUE_LOOKUP: ListBuffer.LazyIterList(locator_iterator),
                       }
            # if Parser.CONTINUE_LOOKUP in needs_env:
            #     context[Parser.CONTINUE_LOOKUP] = list(locator_iterator)
            assert needs_env <= context.keys()
            try:
                ret = ret.eval_ast(self, context)
            except Exception as e:  # TODO: More fine-grained error handling
                if isinstance(e, AssertionError):
                    raise
                ret = CharExceptions.DataError("Error evaluating " + located_key, exception=e)  # TODO: Keep exception?
        return ret

    # TODO: Redo lookup
    def lookup_candidates(self, query: str, *, restricted: bool = None, indices: Iterable[int] = None) -> Generator[Tuple[str, int], None, None]:
        """
        generator that yields all possible candidates for a given query string, implementing our lookup rules.
        The results are pairs (key, index), where index is an index into BaseCharVersion.lists and key is the
        lookup key in that list. The results are in order of precedence.
        It does not check whether the entry exists, just yield candidates.

        the parameter indices is a list of indices where the search is restricted to and also encodes their precedence.

        E.g. if query is "a.b.c" and lists = [0,1], we will yield
        "a.b.c", 0
        "a.b.c", 1
        "a.c", 0
        "a.c", 1
        "c", 0
        "c", 1
        in that order.

        Users rely on the guarantee that the generator only yields finitely many results.

        :param query: query string
        :param restricted: controls whether we only search for restricted keys. Default: restricted-ness of query.
        :param indices: list of indices into BaseCharVersion.lists to restrict the candidates.
        :return: pairs (key, index) where index is an index into self.lists and key is the key for self.lists[index]
        """
        assert Regexps.re_key_any.fullmatch(query)
        if restricted is None:
            restricted = not Regexps.re_key_regular.fullmatch(query)
        if indices is None:
            if restricted:
                indices = self._restricted_lists
            else:
                indices = self._unrestricted_lists

        split_key = query.split('.')
        keylen = len(split_key)
        assert keylen > 0
        main_key = split_key[keylen-1]

        for i in range(keylen-1, -1, -1):
            # prefix = ".".join(split_key[0:i])
            search_key = ".".join(split_key[0:i] + [main_key])
            if restricted and not Regexps.re_key_restrict.fullmatch(search_key):
                # In restricted mode, we only yield restricted search keys.
                # Note that if search_key is not restricted, all further search keys won't be either, so we break.
                break
            for j in indices:
                yield search_key, j
            if main_key == _ALL_SUFFIX:
                continue
            search_key = ".".join(split_key[0:i] + [_ALL_SUFFIX])
            if restricted and not Regexps.re_key_restrict.fullmatch(search_key):
                # Same as above, but if search_key is not restricted, further search keys may become restricted again.
                # (This happens if the main_key part causes search_key to be restricted)
                continue
            for j in indices:
                yield search_key, j
        return

    def function_candidates(self, query: str, *, indices: Iterable[int] = None) -> Generator[Tuple[str, int], None, None]:
        """
        Obtains a list of candidate positions for a function name lookup for query.upper()
        Returns pairs (key, index into lists)

        :param query: function name in lowercase
        :param indices: iterable of indices into self.lists to look in. Defaults to all.
        """
        assert Regexps.re_funcname_lowercased.fullmatch(query)
        if indices is None:
            indices1 = self._restricted_lists
            indices2 = self._unrestricted_lists
        else:
            indices1 = indices2 = indices
        s = '__fun__.' + query
        for j in indices1:
            yield s, j
        s = 'fun.' + query
        for j in indices2:
            yield s, j

    def has_value(self, pair: Tuple[str, int]) -> bool:
        """Check whether candidate pair (as output by function_candidates or lookup_candidates) actually exists"""
        return pair[0] in self.data_sources[pair[1]]

    def find_lookup(self, query: str, indices: Iterable[int] = None) -> Generator[Tuple[str, int], None, None]:
        """
        yield all candidate pairs (lookup_key, index into self.lists) of candidates that match query according
        to our lookup rules for database keys a.b.c
        """
        yield from filter(self.has_value, self.lookup_candidates(query, indices=indices))

    def find_function(self, query: str, indices: Iterable[int] = None) -> Generator[Tuple[str, int], None, None]:
        """
        yield all candidate pairs (lookup_key, index into self.lists) of candidates that match query according
        to our lookup rules for function queries FUNCTION
        """
        yield from filter(self.has_value, self.function_candidates(query, indices=indices))

    def _normalize_action(self, action: dict) -> list:
        """
        Helper function for bulk_process.
        Turns an action (entry of commands argument, which is a dict) into a 3-element list [action-id, target-id, args]
        where action-id is a integral id (that determines the order in which commands are executed)
        target-id is an integral index into lists for this action
        and args is the arguments of type appropriate for the action (an iterable)
        """
        # Note: Code in bulk_process relies on the order given here.
        ret = [None, None, None]
        if action['action'] == 'set_input':
            ret[0] = 1
            if isinstance(acts := action['key_values'], dict):
                ret[2] = acts.items()
            else:
                ret[2] = acts
        elif action['action'] == 'set':
            ret[0] = 2
            if isinstance(acts := action['key_values'], dict):
                ret[2] = acts.items()
            else:
                ret[2] = acts
        elif action['action'] == 'delete':
            ret[0] = 3
            ret[2] = action['keys']
        elif action['action'] == 'get_source':
            ret[0] = 4
            ret[1] = 0  # meaningless. Fixing to an arbitrary constant value.
            ret[2] = action['queries']
            return ret  # to avoid setting ret[1] below
        elif action['action'] == 'get_input':
            ret[0] = 5
            ret[2] = action['keys']
        elif action['action'] == 'get':
            ret[0] = 6
            ret[1] = 0  # meaningless. Fixing to an arbitrary constant value.
            ret[2] = action['queries']
            return ret  # to avoid setting ret[1] below
        else:
            raise ValueError("invalid value for 'action' in command given to bulk_process")
        where: Union[CharDataSourceBase, None, int] = action.get('where')
        if where is None:
            where = self.get_target_index(target_type=action.get('target_type'), target_desc=action.get('target_desc'))
        if not isinstance(where, int):
            where = self._get_index_from_list(where)
        ret[1] = where
        return ret

    def bulk_process(self, commands: list) -> dict:
        """
        This processes multiple get/set/delete actions with one call at once.
        Note that we reorder the actions. The order is arbitrary, except that all modifying operations are executed
        before all querying operations. (Multiple modifications to the same key will give arbitrary results)

        commands is an iterable of commands, where each individual command is a dict of the form
        command = {  'action': one of 'get', 'set', 'get_input', 'delete', 'set_input', 'get_source'
                    'where': (except if action is 'get' / 'get_source') Optional parameter to determine data source
                    'target_type': (except if action is 'get' / 'get_source') Optional parameter to determine data source
                    'target_desc': (except if action is 'get' / 'get_source') Optional parameter to determine data source
                    'keys'/'key_values'/'queries': list of keys (get_input, delete) / key_value-pairs(set/set_input) /
                                                      queries (get / get_source)
                 }
                 Note that for a command {action:'get', 'key_values': args, ...}
                 args may be either a dict or an iterable of key-value pairs. (We call .items() on dicts automatically)

        returns a dict of dict results = {'get': {query1:value1,...},
                                          'get_input': {key1: value1, ...},
                                          'get_source: {query1: result1,...}, (Note that result1 is a pair)
                                         }
        Note:   In case of error, there are no guarantees whatsoever. We might throw an exception and partially perform
                actions.
                TODO: Better error handling

                Note: The whole point of this function is that the actions are reordered
        """
        # turn each command into a triple [action-id:int, target-id:int, args:iterable]
        commands = [self._normalize_action(command) for command in commands]

        # Sort commands lexicographically, primarily by action-id, secondarily by target-id
        commands.sort(key=lambda command: command[1])  # sort by target-id
        commands.sort(key=lambda command: command[0])  # stable-sort by action-id

        # We not wish to collapse all actions with shared target-id and action-id into a single action,
        # with args the concatenation of the individual actions' args (these args are iterables)
        # By using transformations on iterables, we do this in a way that is agnostic to the appropriate container for
        # args; we just concatenates them with itertools.chain.from_iterable

        # group commands according to target-id and action-id:
        commands = itertools.groupby(commands, lambda x: (x[0], x[1], ))

        # Note that commands now is an iterator (tied to the previous value of commands) that returns pairs group_pair == (group-id, group_iterator)
        # where group-id == (command[0], command[1]) is the (target-id, action-id) pair and group_iterator is a (sub-)iterator
        # that iterates all commands [target-id, action-id, args] where (target-id, action-id) matches group-id.
        # Take note of the following restriction of itertools.groupby: Every iterator is single-pass and upon iterating
        # commands, any previously output group_iterator is invalidated.

        # We now get rid of target-id and action-id in each command (it's contained in group-id already), concatenate
        # args with itertools.chain.from_iterable and turn everything into triples again:

        def concat_third(group_iterator):
            return itertools.chain.from_iterable(map(lambda x: x[2], group_iterator))
        processed_commands = map(lambda group_pair: [*group_pair[0], concat_third(group_pair[1])], commands)

        # Be aware that the restrictions from itertools.groupby remain.

        result: Dict[str, Any] = {}
        it = iter(processed_commands)
        changed: bool = False  # whether we changed something

        try:  # ... except StopIteration below.
            action_id: int
            target_it: int
            args: Iterator
            action_id, target_id, args = next(it)

            # This code relies on the order set in _normalize_action

            if action_id <= 3:  # action_ids 1 to 3 are write operations.
                if not self.data_write_permission:
                    raise NoWritePermissionError
                changed = True
            while action_id == 1:  # set_input
                # Note that args is a list of pairs. dict actually converts that. TODO: Change signature of set_inputs?
                self.data_sources[target_id].bulk_set_inputs(key_vals=dict(args))
                action_id, target_id, args = next(it)
            while action_id == 2:  # set
                # again, args is a list of pairs, whereas bulk_set_items requires a dict (TODO: Change that?)
                self.data_sources[target_id].bulk_set_items(key_vals=dict(args))
                action_id, target_id, args = next(it)
            while action_id == 3:  # delete
                self.data_sources[target_id].bulk_del_items(keys=args)
                action_id, target_id, args = next(it)
            if action_id == 4:  # get_source, can appear only once
                assert target_id == 0
                result['get_source'] = self.bulk_get_input_sources(queries=args)
                action_id, target_id, args = next(it)
            if action_id == 5:
                result['get_input'] = {}
            while action_id == 5:  # get_input
                target_id: int
                result['get_input'].update(self.data_sources[target_id].bulk_get_inputs(keys=args))
                action_id, target_id, args = next(it)
            if action_id == 6:  # get, can only appear once
                assert target_id == 0
                result['get'] = self.bulk_get(queries=args)
                __, __, __ = next(it)  # This is guaranteed to raise StopIteration.
            assert False  # _normalize_action takes care of unknown actions, so we can never reach this
        except StopIteration:
            pass
        if changed:
            self._update_last_changed()
        return result
