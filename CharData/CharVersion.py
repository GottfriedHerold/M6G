"""
This module defines a class that is used to hold and access a (version of a) character's data.
Note that characters are versioned in a simple (non-branching) fashion.
The main data that is used to hold the character is a list S = [S0,S1,S2,...] of dict-like objects.
Its keys are PATHS of the form e.g. 'att.st', 'abil.zauberkunde.gfp_spent' (all lowercase, separated by dots)
When looking up e.g. 'abil.zauberkunde.gfp_spent', we actually look for a value in this order:
first, look up S0{abil.zauberkunde.gfp_spent}, then S1{abil.zauberkunde.gfp_spent], ...
then  S0{abil.zauberkunde._all}, S1{abil.zauberkunde._all}, ...
then  S0{abil.gfp_spent}, S1{abil.gfp_spent}, ...
then  S0{abil._all}, S1{abil._all}, ...
then  S0{gfp_spent}, S1{gfp?spent}, ...
finally S0{_all}, S1{_all}, ...
We take the first match we find and return an arbitrary python object.
"""

from datetime import datetime, timezone
from collections import UserDict
import typing
# import itertools
from . import Regexps
from . import Parser
from . import CharExceptions

_ALL_SUFFIX = "_all"

class CharVersion:
    # TODO: add arguments
    def __init__(self, *, creation_time=None, description: str = "", initial_lists: list = None):
        if creation_time is None:
            creation_time: datetime = datetime.now(timezone.utc)
        # TODO : Warn if user-provided creation_time is not TZ-aware (this may lead to issues with Django)
        self.creation_time = creation_time
        self.last_modified = creation_time
        self.description = description
        # TODO: automatically created lists may need handling here (such as directory listings)
        if initial_lists is None:
            self.lists = []
        else:
            self.lists = initial_lists
        return

    def get(self, query, *, locator: typing.Iterable = None):
        """
        Obtain an element from the current CharVersion database by query name.

        locator should usually be None. It encodes the list or a generator of all results that match the query
         name according to our lookup rules. This is overridden to implement $AUTO(QUERY) calls.

        :param query: The key to query for.
        :param locator: (only used for $AUTOQUERY calls)
        :return: database entry. DataError exception if key is not found.
        """
        if locator is None:
            # print('Calling with ' + query + ' empty locator')
            # This creates an generator, that yields all matches for the query key according to our lookup rules.
            locator = self.find_lookup(query)
        # else:
            # print('Calling with ' + query + ' locator= ' + str(locator))

        # brittle: whether get mutates the input locator depends on the type of locator.
        # Namely, if locator is an iterator, it does. If it is a list, it does not.
        # get is used with both cases and we actually NEED that guarantee sometimes.

        # More precisely, locator may be a list or a generator that holds the lookup matches for the query.
        # In the generator case, it === locator and the following try...except block will forward the generator
        # once (unless empty) to find the first match and modify it and locator.
        # If Parser.CONTINUE_LOOKUP is set in ret.needs_env, the remaining matches
        # are copied into a list such that eval_ast can recursively call get with locator = remaining list.
        # In case locator is a list, it != locator: it is just an index into locator and the try...except block
        # will not modify locator. This is important because eval_ast may call get multiple times with the same
        # remaining list.
        it = iter(locator)

        try:
            # where is the index of the list where we found the match, located_key is the key within that list.
            # Often, located_key == query, but located_key may be the fallback key that was actually found according
            # to the lookup rules.
            located_key, where = next(it)
        except StopIteration:
            return CharExceptions.DataError(query + " not found")

        ret = self.lists[where][located_key]

        # If ret is an AST, we need to evaluate it (otherwise, we return the result directly). Note that string literals
        # without = are stored directly, not as ASTs.
        if isinstance(ret, Parser.AST):
            needs_env = ret.needs_env
            context = {'Name': located_key, 'Query': query}
            if Parser.CONTINUE_LOOKUP in needs_env:
                context[Parser.CONTINUE_LOOKUP] = list(it)
                # print('evaluating with context= ' + str(context))
            assert needs_env <= context.keys()
            try:
                ret = ret.eval_ast(self, context)
            except Exception as e:  # TODO: More fine-grained error handling
                if isinstance(e, AssertionError):
                    raise
                ret = CharExceptions.DataError("Error evaluating " + located_key, exception=e)  # TODO: Keep exception?
        return ret

    def lookup_candidates(self, query: str, *, restricted: bool = None, indices: typing.Iterable = None):
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
            indices = range(len(self.lists))

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

    def function_candidates(self, query: str, *, indices: typing.Iterable = None):
        """
        Obtains a list of candidate positions for a function name lookup for query.upper()
        Returns pairs (key, index into lists)

        :param query: function name in lowercase
        :param indices: iterable of indices into self.lists to look in. Defaults to all.
        """
        assert Regexps.re_funcname_lowercased.fullmatch(query)
        if indices is None:
            indices = range(len(self.lists))
        s = '__fun__.' + query
        for j in indices:
            yield s, j
        s = 'fun.' + query
        for j in indices:
            yield s, j

    def has_value(self, pair):
        """Check whether candidate pair (as output by function_candidates or lookup_candidates) actually exists"""
        return pair[0] in self.lists[pair[1]]

    def find_lookup(self, query: str):
        """
        yield all candidate pairs (lookup_key, index into self.lists) of candidates that match query according
        to our lookup rules for database keys a.b.c
        """
        yield from filter(self.has_value, self.lookup_candidates(query))

    def find_function(self, query: str):
        """
        yield all candidate pairs (lookup_key, index into self.lists) of candidates that match query according
        to our lookup rules for function queries FUNCTION
        """
        yield from filter(self.has_value, self.function_candidates(query))


class DataSetTypes:
    """
    Different types of data sets that can be in a char version. These differ slightly in interface and may need to be
    handled differently. This information may be available from DataSet.__class__ as well, in which case we set
    DataSet.dict_type as a class variable, but we want to keep the option to set it on an instance-by-instance basis
    """
    USER_INPUT = "user input"
    CORE_RULES = "core rules"
    USER_RULES = "user rules"
    PREDEFINED_RULES = "predefined rules"
    CACHE_DATASET = "cache"


class UserDataSet(UserDict):
    dict_type = DataSetTypes.USER_INPUT

    # Note: We have no startdict, because we want input_data to be consistent.
    def __init__(self, *, description: str = ""):
        super().__init__()  # empty dict
        self.description = description
        self.input_data = {}

    def set_from_string(self, key, value):
        # check at call site
        assert Regexps.re_key_regular.fullmatch(key)
        if len(value) == 0:
            del self.input_data[key]
            del self[key]
            return
        self.input_data[key] = value
        self[key] = Parser.input_string_to_value(value)

    def get_input(self, key):
        return self.input_data.get(key, None)


class CoreRuleDataSet(UserDict):
    dict_type = DataSetTypes.CORE_RULES

    def __init__(self, desciption: str = "core rules", startdict: dict = None):
        super().__init__()
        self.description = desciption
        if startdict is None:
            startdict = {}
        assert isinstance(startdict, dict)
        self.data = startdict

    def set_from_string(self, key, value):
        assert Regexps.re_key_any.fullmatch(key)
        if len(value) == 0:
            del self[key]
        else:
            self[key] = Parser.input_string_to_value(value)

    # noinspection PyUnusedLocal
    @staticmethod
    def get_input(key):
        return None
