"""
This module defines a class that is used to hold an access a (version of a) character's data.
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


# CORE_RULES: str = "core rules"

class CharVersion:
    # TODO: add arguments
    def __init__(self, *, creation_time=None, description: str = "", initial_lists: list=[]):
        if creation_time is None:
            creation_time: datetime = datetime.now(timezone.utc)
        # TODO : Warn if user-provided creation_time is not TZ-aware (this leads to issues with Django)
        self.creation_time = creation_time
        self.last_modified = creation_time
        self.description = description
        self.initial_lists = initial_lists
        return


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
    def __init__(self, description: str = ""):
        super().__init__()  # empty dict
        self.description = description

class CoreRuleDataSet(UserDict):
    dict_type = DataSetTypes.CORE_RULES
    def __init__(self, desciption: str = "core rules", startdict: dict = {}):
        super().__init__()
        self.description = desciption
        assert isinstance(startdict, dict)
        self.data = startdict