"""
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

The individual data sources need to satisfy a certain interface. Derive from CharDataSource to satisfy it.
Note that BaseCharVersion does not copy its data sources. While a BaseCharVersion object holds a data source in its lists,
do not edit the data source object directly, but through methods provided by BaseCharVersion.
(This is because BaseCharVersion might introduce caching in the future)
"""

# from typing import TYPE_CHECKING

from datetime import datetime, timezone
# from collections import UserDict
# if TYPE_CHECKING:
from typing import List, Optional, Union, Any, Tuple, Generator, Iterable, Callable, TypeVar, Dict, Iterator
# import logging
# logger = logging.getLogger()

# import itertools
from . import Regexps
from . import Parser
from . import CharExceptions
from . import ListBuffer
from . import CharVersionConfig
from functools import wraps
import itertools

from .DataSources import CharDataSource

_Ret_Type = TypeVar("_Ret_Type")
_Arg_Type = TypeVar("_Arg_Type")

_ALL_SUFFIX = "_all"


def _act_on_data_source(action: Callable[..., _Ret_Type], /) -> Callable[..., _Ret_Type]:
    """
    Decorator that takes a BaseCharVersion method action(self, source, ...)
    and turns into a method action(self, ..., where=None, target_type=None, target_desc=None) with keyword-only
    parameters where, target_type, target_desc instead of source.
    The new action calls original action with source as the data source defined by where, target_type and target_desc.
    """
    @wraps(action)  # I do not know how to adjust the type hints for _inner
    def _inner(self: "BaseCharVersion", *args, where: Union[int, None, CharDataSource] = None,
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
    _inner.__annotations__['where'] = 'Union[int, None, CharDataSource]'
    _inner.__annotations__['target_type'] = Optional[str]
    _inner.__annotations__['target_desc'] = Optional[str]
    return _inner


class BaseCharVersion:
    """
    This class models a set of data sources that makes up a character. Note that this is supposed to be subclassed
    in order to add synchronization abilities with a database.
    """

    # these (object-level) attributes are possibly written to by the default implementation.
    # To be overwritten by @property - objects in derived classes to tie to db.

    creation_time: datetime  # only written to if we creation_time is explicitly passed.
    last_change: datetime  # updated at each change
    description: str

    _config: Optional[CharVersionConfig.CVConfig]

    def __init__(self, *, data_sources: List[CharDataSource] = None, config: CharVersionConfig.CVConfig = None, **kwargs):
        """
        Creates a BaseCharConfig. You should set either initial_list or config to initialize its lists (if config is set,
        it will use config to set up the lists). Note that config is the preferred way; the data_sources interface exists
        mostly for debugging and testing purposes, may not be present in subclasses, and may be removed altogether.

        Other keyword-only arguments, if present, forces writing to self; (creation_time, last_change, description).
        These values are never read back in the base class (but written to from multiple places) and are provided for derived classes.
        """

        # Note that we do not have a make_from_config staticmethod that calls __init__, because
        # config needs to be associated to the CharVersion object before config.setup_managers() and config.make_data_sources() is called.
        # (This should not really matter much for config.setup_managers, but we need to give config.make_data_source()
        # the option to inspect and modify the CharVersion object. In particular, data sources that refer to the DB
        # may need to to obtain the primary key of the CharVersion object.)
        self._config = config
        if config is not None:
            if data_sources:
                raise ValueError("Do not provide both initial lists and config")
            config.char_version = self  # consider turning into a weak-ref
            config.setup_managers()
            self._data_sources = config.make_data_sources()

        elif data_sources is None:
            self._data_sources = []
        else:
            self._data_sources = data_sources

        # Internally used to speed up lookups:
        self._unrestricted_lists = []  # indices of data sources that contain unrestricted keys in lookup order
        self._restricted_lists = []  # indices of data sources that contain restricted keys in lookup order
        self._type_lookup = {}  # first index of data source for a given dict_type
        self._desc_lookup = {}  # first index of data source for a given description
        self._default_target = None  # index that writes go by default

        # These parameters are only set if they occur in kwargs at all
        # (Note that creation_time = None is handled differently from creation_time not present)
        # We expect that derived classes override self.creation_time as a @property to tie it to a database.
        # So we need to keep the option
        if "creation_time" in kwargs:
            if kwargs["creation_time"]:
                self.creation_time: datetime = kwargs["creation_time"]
            else:
                self.creation_time: datetime = datetime.now(timezone.utc)
            self.last_change: datetime = self.creation_time
        elif "last_change" in kwargs:
            self.last_change: datetime = kwargs["last_change"]
        if "description" in kwargs:
            self.description: str = kwargs["description"]
        self._update_list_lookup_info()
        return

    # def __enter__(self):
    #     pass

    # def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
    #    return False

    @property
    def data_sources(self) -> List[CharDataSource]:
        return self._data_sources

    @data_sources.setter
    def data_sources(self, new_lists, /):
        self._data_sources = new_lists
        self._update_list_lookup_info()

    @property
    def config(self) -> Optional[CharVersionConfig.CVConfig]:
        return self._config

    #  setter for config? We basically would need to create a new object

    def _update_list_lookup_info(self) -> None:
        """
        Called to update internal data related to lookup on the data sources.
        Note that modifying list by an external caller is not recommended anyway.
        Also note that BaseCharVersion().lists.insert(...) bypasses @lists.setter.
        May needs to be called externally after self.lists changes (which you should not do)
        """
        self._unrestricted_lists = []
        self._restricted_lists = []
        self._type_lookup = {}
        self._desc_lookup = {}
        self._default_target = None

        for i in range(len(self.data_sources)):
            list_i: CharDataSource = self.data_sources[i]
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

    def _get_index_from_list(self, source: CharDataSource) -> int:
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
    # This is why we seemingly redefine those functions. The stub above is the actual signature.
    # This is to prevent IDEs / type checkers from providing misinformation.

    def get_data_source(self, *, where: Union[CharDataSource, int, None] = None, target_type: Optional[str] = None, target_desc: Optional[str] = None) -> CharDataSource: ...
    @_act_on_data_source
    def get_data_source(self, source: CharDataSource) -> CharDataSource:
        return source

    def set(self, key: str, value: object, *, where: Union[CharDataSource, int, None] = None, target_type: Optional[str] = None, target_desc: Optional[str] = None) -> None: ...
    @_act_on_data_source
    def set(self, source: CharDataSource, key: str, value: object) -> None:
        source[key] = value
        self.last_change = datetime.now(timezone.utc)

    def bulk_set(self, key_values: Dict[str, object], *, where: Union[CharDataSource, int, None] = None, target_type: Optional[str] = None, target_desc: Optional[str] = None) -> None: ...
    @_act_on_data_source
    def bulk_set(self, source: CharDataSource, key_values: Dict[str, object]) -> None:
        source.bulk_set_items(key_values)
        self.last_change = datetime.now(timezone.utc)

    def set_input(self, key: str, value: str, *, where: Union[CharDataSource, int, None] = None, target_type: Optional[str] = None, target_desc: Optional[str] = None) -> None: ...
    @_act_on_data_source
    def set_input(self, source: CharDataSource, key: str, value: str) -> None:
        source.set_input(key, value)
        self.last_change = datetime.now(timezone.utc)

    def bulk_set_input(self, key_values: Dict[str, str], *, where: Union[CharDataSource, int, None] = None, target_type: Optional[str] = None, target_desc: Optional[str] = None) -> None: ...
    @_act_on_data_source
    def bulk_set_input(self, source: CharDataSource, key_values: Dict[str, str]) -> None:
        source.bulk_set_inputs(key_values)

    def delete(self, key: str, *, where: Union[CharDataSource, int, None] = None, target_type: Optional[str] = None, target_desc: Optional[str] = None) -> None: ...
    @_act_on_data_source
    def delete(self, source: CharDataSource, key: str) -> None:
        """
        Deletes data_source[key] where data_source is specified by where / target_type / target_desc.
        Trying to deleting keys that do not exist in the data_source may trigger an exception, as per Python's default.
        """
        del source[key]
        self.last_change = datetime.now(timezone.utc)

    def bulk_delete(self, keys: Iterable[str], *, where: Union[CharDataSource, int, None] = None, target_type: Optional[str] = None, target_desc: Optional[str] = None) -> None: ...
    @_act_on_data_source
    def bulk_delete(self, source: CharDataSource, keys: Iterable[str]) -> None:
        source.bulk_del_items(keys)
        self.last_change = datetime.now(timezone.utc)

    def get_input(self, key: str, default: str, *, where: Union[CharDataSource, int, None] = None, target_type: Optional[str] = None, target_desc: Optional[str] = None) -> str: ...
    @_act_on_data_source
    def get_input(self, source: CharDataSource, key: str, default: str = "") -> str:
        """
        Gets the input string that was used to set data_source[key] in the data_source specified by where / target_type / target_desc.

        Note about data_source behaviour:
        If data_source supports input_lookup, but key is not present, this returns default (empty string unless specified).
        If data_source does not support input_lookup, we return either None or some information string.
        We do NOT raise an exception.

        See also get_input_source for a version that determines data_source from the key.
        """
        return source.get_input(key, default=default)

    def bulk_get_inputs(self, keys: Iterable[str], default: str = "", *, where: Union[CharDataSource, int, None] = None, target_type: Optional[str] = None, target_desc: Optional[str] = None) -> Dict[str, str]: ...
    @_act_on_data_source
    def bulk_get_inputs(self, source: CharDataSource, keys: Iterable[str], default: str = "") -> Dict[str, str]:
        return source.bulk_get_inputs(keys, default=default)

    def find_query(self, key: str, *, indices: Optional[Iterable[int]] = None) -> Tuple[str, int]:
        """
        Find where a given (non-function) query string is located in self.lists
        :param key: query string
        :param indices: None or list of indices to restrict lookup rules to
        :return: pair (query, index) such that self.lists[index][query] is where the lookup for key ends up
        """
        try:
            return next(self.find_lookup(key, indices=indices))
        except StopIteration:
            raise LookupError

    def get_input_source(self, key: str, *, default=("", True)) -> Tuple[str, bool]:
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
            query, where = self.find_query(key)
        except LookupError:
            return default
        # Note that get_input should not throw an exception when stores_input_data is False,
        # but rather return some value indicating error (None, "", or an error message string)
        return self.get_input(query, where=where), self.data_sources[where].stores_input_data

    def bulk_get_input_sources(self, keys: Iterable[str], *, default=("", True)) -> Dict[str, Tuple[str, bool]]:
        return {key: self.get_input_source(key, default=default) for key in keys}

    def bulk_get(self, queries: Iterable[str], default=None) -> Dict[str, Any]:
        return {key: self.get(key, default=default) for key in queries}

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
        where: Union[CharDataSource, None, int] = action.get('where')
        if where is None:
            where = self.get_target_index(target_type=action.get('target_type'), target_desc=action.get('target_desc'))
        if not isinstance(where, int):
            where = self._get_index_from_list(where)
        ret[1] = where
        return ret

    def bulk_process(self, commands: list) -> dict:
        """
        This processes multiple get/set/delete actions with one call once.
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
                result['get_source'] = self.bulk_get_input_sources(keys=args)
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
            self.last_change = datetime.now(timezone.utc)
        return result
