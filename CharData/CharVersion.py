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
import itertools
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
        if initial_lists is None:
            self.lists = []
        else:
            self.lists = initial_lists
        return

    def get(self, key, *, loc_fun: bool = False):
        if loc_fun:
            located_key, where = self.locate_function(key)  # TODO
        else:
            assert Regexps.re_key_any.fullmatch(key)
            located_key, where = self.locate(key, restrict=Regexps.re_key_restrict.fullmatch(key))
        if where is None:
            return CharExceptions.DataError(key + " not found")
        ret = self.lists[where][located_key]
        if isinstance(ret, Parser.AST):
            context = {'Name': located_key, 'Query': key}
            try:
                ret = ret.eval_ast(self, context)
            except Exception as e:
                ret = CharExceptions.DataError("Error evaluating " + key, exception=e)
        return ret

    def lookup_candidates(self, query: str, restricted: bool = False):
        assert Regexps.re_key_any.fullmatch(query)
        if restricted:
            assert Regexps.re_key_restrict.fullmatch(query)
        length = len(self.lists)
        # length = 3
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
            for j in range(length):
                yield (search_key, j)
            if main_key == _ALL_SUFFIX:
                continue
            search_key = ".".join(split_key[0:i] + [_ALL_SUFFIX])
            if restricted and not Regexps.re_key_restrict.fullmatch(search_key):
                # Same as above, but if search_key is not restricted, further search keys may become restricted again.
                # (This happens if the main_key part causes search_key to be restricted)
                continue
            for j in range(length):
                yield (search_key, j)
        return

    def find_lookup(self, query: str):
        yield from filter(lambda pair: pair[0] in self.lists[pair[1]],  self.lookup_candidates(query))


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
    def __init__(self, desciption: str = "core rules", startdict: dict = {}):
        super().__init__()
        self.description = desciption
        assert isinstance(startdict, dict)
        self.data = startdict

    def set_from_string(self, key, value):
        assert Regexps.re_key_any.fullmatch(key)
        if len(value) == 0:
            del self[key]
        else:
            self[key] = Parser.input_string_to_value(value)

    def get_input(self, key):
        return None
