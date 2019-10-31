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
from . import Regexps
from . import Parser
from . import CharExceptions


_ALL_SUFFIX = "_all"

def input_string_to_value(input_string: str):
    if len(input_string) == 0:
        return None
    # "STRING or "STRING" or 'STRING or 'STRING' all parse as strings
    if input_string[0] == '"' or input_string[0] == "'":
        if input_string[-1] == input_string[0]:
            return input_string[1:-1]
        else:
            return input_string[1:]
    elif input_string[0] == '=':
        try:
            result = Parser.parser.parse(input_string[1:])
        except Exception as e:
            result = CharExceptions.DataError(exception=e)
        return result
    elif Regexps.re_number_int.fullmatch(input_string):
        return int(input_string)
    elif Regexps.re_number_float.fullmatch(input_string):
        return float(input_string)
    else:
        return input_string

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
            if Regexps.re_key_restrict.fullmatch(key):
                located_key, where = self.locate_restricted(key, restrict=Regexps.re_key_restrict.fullmatch(key))
        if where is None:
            return CharExceptions.DataError(key + " not found")
        ret = self.lists[where][located_key]
        if isinstance(ret, Parser.AST):
            context = {'Name': located_key}
            try:
                ret = ret.eval_ast(self, context)
            except Exception as e:
                ret = CharExceptions.DataError("Error evaluating " + key, exception=e)
        return ret
            
        

    def locate(self, key: str, *, startafter = None, restrict = False):
        # Check at call site. TODO: Verify this! (Otherwise, raise Exception)
        if restrict:
            assert Regexps.re_key_restrict.fullmatch(key)
        else:
            assert Regexps.re_key_regular.fullmatch(key)
        L = len(self.lists)
        # L = 3  #  for debug
        split_key = key.split('.')
        keylen = len(split_key)
        main_key = split_key[keylen-1]
        

        # This is really 2 for-loops, but we need to be able to start in the middle of an inner loops.
        # So it becomes easier to write it as a single while-loop
        
        if startafter:
            j = startafter[1]
            current = startafter[0].split('.')
            search_key = startafter[0]
            i = len(current) - 1
            postfix = current[-1]
        else:
            i = keylen # length of prefix to take
            j = L-1 #
            postfix = _ALL_SUFFIX
        while True:
            j+=1
            if j == L:
                j = 0
                if postfix == _ALL_SUFFIX:  # comparison with == rather than is (because main_key == ALL_SUFFIX is possible)
                    postfix = main_key
                    i-=1
                    if i == -1:
                        return None, None
                else:
                    postfix = _ALL_SUFFIX
                search_key = ".".join(split_key[0:i] + [postfix])
                if restrict and Regexps.re_key_regular.fullmatch(search_key):
                    j = L - 1
                    continue
            # print (search_key, j)
            if search_key in self.lists[j]:
                return search_key, j
        
        

        
        #for i in range(keylen-1, -1,-1):
        #    prefix = ".".join(split_key[0:i])
        #    search_key = prefix + "." + main_key
        #    for j in range(L):
        #    #   print(search_key, j) -- debug
        #        if search_key in self.lists[j]:
        #            return search_key, j
        #    search_key = prefix + "._all"
        #    for j in range(L):
        #    #   print(search_key, j)  -- debug
        #        if search_key in self.lists[j]:
        #            return search_key, j
        #return None, None

    
    def locate_function(self, key: str):
        main_key = key.lower()
        L = len(self.lists)
        search_key = "__fun__" + main_key
        for j in range(L):
            if search_key in self.lists[j]:
                return search_key, j
        search_key = "_fun" + main_key
        for j in range(L):
            if search_key in self.lists[j]:
                return search_key, j
        return None, None
            


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
        self[key] = input_string_to_value(value)

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
            self[key] = input_string_to_value(value)

    def get_input(self, key):
        return None
