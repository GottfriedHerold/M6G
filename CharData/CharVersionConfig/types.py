"""
    This file defines the data types involved in character metadata. This mostly means Enums, TypedDicts and dataclasses
    for better static type checking.

    A CVConfig instance holds a manages metadata for a CharVersion. To achieve db persistence that is easy to
    serialize / make an UI for / update between versions of CharsheetGen, we use JSON to serialize these as string.

    Of course, to serialize the manager objects, we rather store the arguments needed to (re-)create them, which we
    call a (Python/JSON) recipe.

    The Python format can be either a dict or a dataclass (dicts are just an intermediate and used to write them down
    concisely). The parsing/serializing is JSON <-> dict <-> dataclass

    As a dict, the format is as follows:

    recipe = {
        ... other Metadata (TODO)
        'edit_mode': int (EditModes.FOO.value, on the dict level we do not use EnumTypes)
        'data_source_order': list of ints (a permutation of 0,1,2, ...) that index into the list of data source descriptions,
                             which are in turn defined by the managers.
        'managers': list of manager creation instructions
    }

    each manager instruction in turn is a dict
    {
        'type_id' : "some_string",  # type-identifier, see below
        'module' : "some module identifier", see below.
        'args' : [some_JSON_able_list]   # defaults to empty list
        'kwargs' : {'some' : 'JSON_able_dict'}  # defaults to empty dict
        'group': 'name of group'  # Name of group this instruction belongs to. Used for display options only.
    }

    type_id is a string that uniquely identifies the Manager class (or, more generally, a callable that is to be called
    with args and kwargs and returns a manager). module is the python import path of a module that is imported if
    type_id is not recognized.
    (In order for type_id to work, managers need to register with the CVConfig class. This is done upon import of the
    appropriate module. Note that the base class of the managers has a __init__subclass__ hook that deals with all of
    that automatically)

    To achieve persistence in db, we need that kwargs and args are appropriately JSON-serializable.
    We restrict this further by requiring that all dict-keys are strings and we disallow floats.
    It is not recommended to use Non-ASCII characters in strings.
    (This means we allow None, bool, str, int as well as dicts and lists recursively built from that.
    Note that JSON is not able to distinguish object identity from equality, so with x=[], y=[], the difference between
    L1 = [x,x] and L2 = [x,y] is lost to JSON as well as references held to existing objects)
"""
from __future__ import annotations
import dataclasses
# NOTE: dataclasses-json is not deemed mature enough, so we do everything manually
from typing import TypedDict, Final, List
from enum import Enum

from .EditModes import EditModes

# May be changed to dict!

class ManagerInstructionGroups(Enum):
    default = 'default'
    core = 'core'


class ManagerInstructionsDictBase(TypedDict):
    type_id: str
    module: str


class ManagerInstructionsDict(ManagerInstructionsDictBase):
    args: list
    kwargs: dict
    group: str  # key to ManagerInstructionsGroup

@dataclasses.dataclass
class ManagerInstructions:
    type_id: str
    module: str
    group: ManagerInstructionGroups
    args: list = dataclasses.field(default_factory=list)
    kwargs: dict = dataclasses.field(default_factory=dict)

    @classmethod
    def from_nested_dict(cls, /, group: str, **kwargs):
        return cls(group=ManagerInstructionGroups(group), **kwargs)

    def as_dict(self, /) -> ManagerInstructionsDict:
        return dataclasses.asdict(self)

    def make_copy(self, /) -> 'ManagerInstructions':
        return dataclasses.replace(self)


class PythonConfigRecipeDict(TypedDict):
    edit_mode: int  # key to EditModes
    data_source_order: List[int]
    managers: List[ManagerInstructionsDict]

@dataclasses.dataclass
class PythonConfigRecipe:
    edit_mode: EditModes
    data_source_order: List[int]
    managers: List[ManagerInstructions]

    @classmethod
    def from_nested_dict(cls, /, edit_mode: int, data_source_order: List[int], managers: List[ManagerInstructionsDict]):
        return cls(edit_mode=EditModes(edit_mode), data_source_order=data_source_order,
                   managers=list(map(lambda m_instruction_dict: ManagerInstructions.from_nested_dict(**m_instruction_dict), managers)))

    def as_dict(self, /) -> PythonConfigRecipeDict:
        return dataclasses.asdict(self)

    def make_copy(self, /) -> 'PythonConfigRecipe':
        return dataclasses.replace(self)

def validate_strict_JSON_serializability(arg, /) -> None:
    """
    Checks whether the given argument is a python object that adheres to our JSON-serializability restrictions.
    (Note that we are stricter that JSON proper). In case of non-adherence, we raise a ValueError.
    """
    if (arg is None) or type(arg) in [int, bool, str]:
        return
    elif type(arg) is list:  # No sub-typing! Also, fail on tuples.
        for item in arg:
            validate_strict_JSON_serializability(item)
        return
    elif type(arg) is dict:
        for key, value in arg.items():
            if type(key) is not str:
                raise ValueError("Invalid CVConfig: non-string dict key")
            validate_strict_JSON_serializability(value)
        return
    else:
        raise ValueError("Invalid CVConfig: Contains non-allowed python type")


EMPTY_RECIPE_DICT: Final[PythonConfigRecipeDict] = {
    'edit_mode': EditModes.NORMAL,
    'data_source_order': [],
    'managers': []
}
EMPTY_RECIPE: Final[PythonConfigRecipe] = PythonConfigRecipe.from_nested_dict(**EMPTY_RECIPE_DICT)
