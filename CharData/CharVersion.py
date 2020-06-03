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

The CharVersion class itself only takes care about managing these dict-like data sources and the lookup.
To actually use it, you will probably have to subclass it and override/add some @property-methods to tie
a CharVersion's metadata not contained in self.lists such as last_change to a database.

The individual data sources need to satisfy a certain interface. Derive from CharDataSource to satisfy it.
Note that CharVersion does not copy its data sources. While a CharVersion object holds a data source in its lists,
do not edit the data source object directly, but through methods provided by CharVersion.
(This is because CharVersion might introduce caching in the future)
"""

# from typing import TYPE_CHECKING

from datetime import datetime, timezone
# from collections import UserDict
# if TYPE_CHECKING:
from typing import List, Optional, Union, Any, Tuple, Generator, Iterable, Callable, TypeVar, Dict
from collections.abc import MutableMapping, Mapping

# import itertools
from . import Regexps
from . import Parser
from . import CharExceptions
from . import ListBuffer
from functools import wraps

_Ret_Type = TypeVar("_Ret_Type")
_Arg_Type = TypeVar("_Arg_Type")

_ALL_SUFFIX = "_all"

class CharVersion:
    """
    This class models a set of data sources that makes up a character. Note that this is supposed to be subclassed
    in order to add synchronization abilities with a database.
    """

    # these (object, not class-)attributes are possibly written to.
    # To be overwritten by @property - objects in derived classes to tie to db.

    creation_time: datetime  # only written to if we creation_time is explicitly passed.
    last_change: datetime  # updated at each change
    description: str

    def __init__(self, *, initial_lists: "List[CharDataSource]" = None, **kwargs):
        if initial_lists is None:
            self._lists = []
        else:
            self._lists = initial_lists

        # Internally used to speed up lookups:
        self.unrestricted_lists = []  # indices of data sources that contain unrestricted keys in lookup order
        self.restricted_lists = []  # indices of data sources that contain restricted keys in lookup order
        self.type_lookup = {}  # first index of data source for a given dict_type
        self.desc_lookup = {}  # first index of data source for a given description
        self.default_target = None  # index that writes go by default

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
        self.update_metadata()
        return

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        return False

    @property
    def lists(self) -> "List[CharDataSource]":
        return self._lists

    @lists.setter
    def lists(self, new_lists):
        self._lists = new_lists
        self.update_metadata()

    def update_metadata(self) -> None:
        """
        Called to update internal data. Needs to be externally called after lists change.
        E.g. after x.lists.insert for CharVersion object x.
        TODO: This interface is not stable
        :return: None
        """
        self.unrestricted_lists = []
        self.restricted_lists = []
        self.type_lookup = {}
        self.desc_lookup = {}
        self.default_target = None

        for i in range(len(self.lists)):
            list_i: CharDataSource = self.lists[i]
            if list_i.contains_restricted:
                self.restricted_lists += [i]
            if list_i.contains_unrestricted:
                self.unrestricted_lists += [i]
            if list_i.dict_type not in self.type_lookup:
                self.type_lookup[list_i.dict_type] = i
            elif list_i.type_unique:
                raise RuntimeError("Can only put one DataSource of type " + list_i.dict_type + " into CharVersion")
            self.desc_lookup.setdefault(list_i.description, i)
            if list_i.default_write:
                self.default_target = i

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
                return self.default_target
            else:
                return self.desc_lookup[target_desc]
        else:
            if target_desc is None:
                return self.type_lookup[target_type]
            else:
                return next(filter(lambda i: self.lists[i].dict_type == target_type and self.lists[i].description == target_desc, range(len(self.lists))), None)

    # @staticmethod -- this does not work due to subtle details of how class creation works. Calling action unbound does the trick.
    def act_on_data_source(action: Callable[..., _Ret_Type]) -> Callable[..., _Ret_Type]:
        @wraps(action)
        def _inner(self: "CharVersion", *args, where: "Union[int, None, CharDataSource]" = None, target_type: Optional[str] = None, target_desc: Optional[str] = None, **kwargs) -> _Ret_Type:
            if where is None:
                where = self.get_target_index(target_type, target_desc)
            if isinstance(where, int):
                return action(self, self.lists[where], *args, **kwargs)
            else:
                if where not in self.lists:
                    raise LookupError("Invalid data source: Not in this CharVersion's data list.")
                return action(self, where, *args, **kwargs)
        return _inner

    @act_on_data_source
    def get_data_source(self, source):
        return source

    @act_on_data_source
    def set(self, source: "CharDataSource", key: str, value: object) -> None:
        source[key] = value
        self.last_change = datetime.now(timezone.utc)

    @act_on_data_source
    def bulk_set(self, source: "CharDataSource", key_vals: Dict[str, object]) -> None:
        source.bulk_set_items(key_vals)
        self.last_change = datetime.now(timezone.utc)

    @act_on_data_source
    def set_input(self, source: "CharDataSource", key: str, value: str) -> None:
        source.set_input(key, value)
        self.last_change = datetime.now(timezone.utc)

    @act_on_data_source
    def bulk_set_input(self, source: "CharDataSource", key_vals: Dict[str, str]) -> None:
        source.bulk_set_inputs(key_vals)

    @act_on_data_source
    def delete(self, source: "CharDataSource", key: str) -> None:
        """
        Deletes data_source[key] where data_source is specified by where / target_type / target_desc.
        Trying to deleting keys that do not exist in the data_source may trigger an exception, as per Python's default.
        """
        del source[key]
        self.last_change = datetime.now(timezone.utc)

    @act_on_data_source
    def bulk_delete(self, source: "CharDataSource", keys: Iterable[str]) -> None:
        source.bulk_del_items(keys)
        self.last_change = datetime.now(timezone.utc)

    @act_on_data_source
    def get_input(self, source: "CharDataSource", key: str, default: str = "") -> str:
        """
        Gets the input string that was used to set data_source[key] in the data_source specified by where / target_type / target_desc.

        Note about data_source behaviour:
        If data_source supports input_lookup, but key is not present, this returns default (empty string unless specified).
        If data_source does not support input_lookup, we return either None or some information string.
        We do NOT raise an exception.

        See also get_input_source for a version that determines data_source from the key.
        """
        return source.get_input(key, default=default)

    @act_on_data_source
    def bulk_get_inputs(self, source: "CharDataSource", keys: Iterable[str], default: str = "") -> Dict[str, str]:
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
        return self.get_input(query, where=where), self.lists[where].stores_input_data

    def bulk_get_input_sources(self, keys: str, *, default=("", True)) -> Dict[str, Tuple[str, bool]]:
        return {key: self.get_input_source(key, default=default) for key in keys}

    def bulk_get(self, queries: Iterable[str], default=None) -> Dict[str, Any]:
        return {key: self.get(key, default=default) for key in queries}

    def get(self, query: str, *, locator: Iterable = None, default=None) -> Any:
        """
        Obtain an element from the current CharVersion database by query name.

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
        # However, if this output is an AST like parse('=$AUTO + $AUTO'), evaluation of that will recursively call
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

        ret = self.lists[where][located_key]

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
        The results are pairs (key, index), where index is an index into CharVersion.lists and key is the
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
        :param indices: list of indices into CharVersion.lists to restrict the candidates.
        :return: pairs (key, index) where index is an index into self.lists and key is the key for self.lists[index]
        """
        assert Regexps.re_key_any.fullmatch(query)
        if restricted is None:
            restricted = not Regexps.re_key_regular.fullmatch(query)
        if indices is None:
            if restricted:
                indices = self.restricted_lists
            else:
                indices = self.unrestricted_lists

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
            indices1 = self.restricted_lists
            indices2 = self.unrestricted_lists
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
        return pair[0] in self.lists[pair[1]]

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

    def bulk_process(self, actions: list) -> dict:
        """
        This processes multiple get/set/delete actions at once. Note that there is no guarantee about order.

        :param actions:
        :return:
        """
        raise NotImplementedError


class CharDataSource:
    """
    Abstract Base class for Char Data sources.
    This implements some common behaviour and is supposed to be overridden.
    """
    contains_restricted: bool = True  # Data source may contain restricted keys. Not necessarily enforced.
    contains_unrestricted: bool = True  # Data source may contain unrestricted keys.
    # description and dict_type are string that describe the data source.
    # If unique, CharVersion can look up the data source by this.
    description: str = "nondescript"
    dict_type: str = "user defined"
    default_write: bool = False  # Writes go into this data source by default. At most one data source per CharVersion.
    read_only: bool = False  # Cannot write / delete if this is set.
    stores_input_data: bool  # stores input data.
    stores_parsed_data: bool  # stores parsed data.
    type_unique: bool = False  # Only one data source with the given dict_type must be present in a CharVersion.

    # One or both of these two need to be set by a derived class to make CharDataSource's default methods work:
    input_data: "Union[Mapping, MutableMapping]"  # self.storage is where input data is stored if stored_input_data is set
    parsed_data: "Union[Mapping, MutableMapping]"  # self.parsed_data is where parsed data is stored if stores_parsed_data is set

    input_parser = staticmethod(Parser.input_string_to_value)  # parser to transform input values to parsed_data.

    def _check_key(self, key: str) -> bool:
        """
        The default implementation runs this on keys before some operations to check whether the key may even be
        in input_data resp. parsed_data. This is purely an optimization for the case where
        lookups in stores_input_data or stores_parsed_data are expensive (i.e. database access)
        Always returning true is perfectly fine. It is up to the concrete class to ensure this optimization works.
        Do not rely on the setters checking this.
        :param key: key to look up
        :return: False if we can somehow guarantee that this key does not belong into this data source.
        """
        if not Regexps.re_key_any.fullmatch(key):
            return False
        if not self.contains_restricted and Regexps.re_key_restrict.fullmatch(key):
            return False
        if not self.contains_unrestricted and not Regexps.re_key_restrict.fullmatch(key):
            return False
        return True

    def __contains__(self, key: str) -> bool:
        """
        Checks if key is contained in the data source
        """
        if not self._check_key(key):
            return False
        if self.stores_input_data:
            return key in self.input_data
        else:
            return key in self.parsed_data

    def __getitem__(self, key: str) -> Any:
        """
        Gets the parsed item stored under this key.
        """
        if self.stores_parsed_data:
            return self.parsed_data[key]
        else:
            return self.input_parser(self.input_data[key])

    def bulk_get_items(self, keys: Iterable[str]) -> Dict[str, Any]:
        """
        Get multiple data. Returns a dict. May be overridden for efficiency.
        """
        return {key: self[key] for key in keys}

    def __setitem__(self, key: str, value: object) -> None:
        """
        Sets the ("parsed", i.e. raw python) value stored under key.
        Note that if the data source stores input data, this function makes no sense.
        """
        if not self._check_key(key):
            raise KeyError("Data source does not support storing this key")
        if self.stores_input_data or self.read_only:
            raise TypeError("Data source does not support storing parsed data")
        self.parsed_data[key] = value

    def bulk_set_items(self, key_vals: Dict[str, object]) -> None:
        """
        sets several parsed data at once. May be overridden for efficiency
        """
        for key, val in key_vals.items():
            self[key] = val

    def __delitem__(self, key: str) -> None:
        """
        Deletes the key from the data source. This assumes that the key was present beforehand.
        """
        if not self._check_key(key):
            raise KeyError("Data source does not support deleting this key")
        if self.stores_parsed_data:
            del self.parsed_data[key]
        if self.stores_input_data:
            del self.input_data[key]

    def bulk_del_items(self, keys: Iterable[str]) -> None:
        """
        Deletes the keys from the data source. Works like __delitem__. May be overridden for efficiency.
        """
        for key in keys:
            del self[key]

    def get_input(self, key: str, default="") -> Optional[str]:
        """
        Gets the input data associated to the key, or default = "" if not found.

        Note: If we do not store input data, returns None. This may be overwritten by a derived class to return
        an error message string. It must not throw an exception.
        The default = "" behaviour must NOT be overwritten.
        """
        if not self.stores_input_data:
            return None
        else:
            try:
                return self.input_data[key]
            except KeyError:
                return default

    def bulk_get_inputs(self, keys: Iterable[str], default="") -> Dict[str, str]:
        """
        Gets several input data at once. May be overwritten for more efficiency.
        Returns a dict key:value with value as in get_input
        """
        return {key: self.get_input(key, default=default) for key in keys}

    def set_input(self, key: str, value: str) -> None:
        """
        Stores value (as an input string, to be parsed with input_parser) under key.
        Storing an empty value will delete the key, if it was present before.
        """
        if self.read_only:
            raise TypeError("Data source is read-only")
        if not self._check_key(key):
            raise KeyError("Data source does not support storing this key")
        if not value:
            try:
                del self[key]
            except KeyError:
                pass
        else:
            if self.stores_input_data:
                self.input_data[key] = value
            if self.stores_parsed_data:
                self.parsed_data[key] = self.input_parser(value)

    def bulk_set_inputs(self, key_vals: Dict[str, str]) -> None:
        """
        Sets several inputs at once. input is a dict {key, vals}
        """
        for key, val in key_vals.items():
            self.set_input(key, val)

    def __str__(self) -> str:
        return "Data source of type " + self.dict_type + ": " + self.description


class CharDataSourceDict(CharDataSource):
    """
    Wrapper dicts (one for input data / one for parsed) -> CharDataSource. Used for testing.
    """
    dict_type = "Char data source dict"
    stores_input_data = True
    stores_parsed_data = True

    def __init__(self):
        self.input_data = dict()
        self.parsed_data = dict()