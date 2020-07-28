"""
    This file defines the data types involved in character metadata. This mostly means Enums, TypedDicts and dataclasses
    for better static type checking.

    A CVConfig instance holds a manages metadata for a CharVersion. To achieve db persistence that is easy to
    serialize / make an UI for / update between versions of CharsheetGen, we use JSON to serialize these as string.

    Of course, to serialize the manager objects, we rather store the arguments needed to (re-)create them, which we
    call a (Python/JSON) recipe.

    The Python format can be either a dict or a dataclass (dicts are just an intermediate steps, used to write them down
    concisely and to simplify JSON (de)serialization). The parsing/serializing is JSON <-> dict <-> dataclass

    As a dict, the format is as follows:

    recipe = {
        ... other Metadata (TODO)
        'edit_mode': int (EditModes.FOO.value, on the dict level we do not use EnumTypes)
        'data_source_order': list of ints (a permutation of 0,1,2, ...) that index into the list of data source descriptions,
                             which are in turn defined by the managers.
        'manager_instructions': list or dict of manager creation instructions (dict is keyed by uuid)
    }

    each manager instruction in turn is a dict
    {
        'type_id' : "some_string",  # type-identifier, see below
        'module' : "some module identifier", see below.
        'args' : [some_JSON_able_list],   # defaults to empty list
        'kwargs' : {'some' : 'JSON_able_dict'},  # defaults to empty dict
        'group': 'name of group',  # Name of group this instruction belongs to. Used for display options only.
        'uuid': some_int, # a unique (within the recipe, at least) identifier. If None or missing, will be set automatically.
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
from typing import TypedDict, Final, List, Dict, Union, Any
from enum import Enum, IntEnum
import re
import logging

from .EditModes import EditModes

# May be changed to dict!


class ManagerInstructionGroups(Enum):
    default = 'default'
    core = 'core'


# UUIDs are used to create references between objects contained within a single character version's metadata.
# These references need to be able to survive (de)serialization, ideally even of subobjects.
# There are several (somewhat conflicting) requirements of UUIDs.
# - We use essentially the same format(s) for writing down the initial setup as we use for serialization.
#   However, when writing down the initial setup, we may not have the context needed to create UUIDs.
#   Note that this is never supposed to happen when serializing.
# - Due to the above, we want to be able to write down configs and want uuid's to be concise.
# - We want to be able to edit the DB by hand in a pinch.
# - UUIDs should be able to be used as dictionary keys (so need to be hashable)
# - Uniqueness is only required within a given char version. Stupidly copying all data associated to a given
#   CharVersion should preserve the reference structure.
# - We may need to globally rename a uuid to a different value. This violates the first u in uuid, but may be
#   needed.
# - JSON serialization throws away type information. We need to be able to recognize uuids as such in JSON serialized
#   formats to achieve the above. This is done by knowing when to expect a uuid.
# - UUIDs will appear in Javascript strings and GET/POST request strings, possibly as substrings of something.
#   Due to this (note 1 vs "1" in JS), we need to make __str__ injective, output only safe characters and possibly have
#   UUID.__str__ self-delineate.

UUID_Source = Union[int, str]


class UUID:
    __slots__ = ['value']
    value: UUID_Source
    re_valid_str: Final = re.compile(r"[a-zA-Z]+")  # Valid string uuids. We are rather restrictive here.

    def __init__(self, value: Union[int, str, UUID], /):
        if type(value) is UUID:
            self.value = value.value
        else:
            self.value = value

    def __eq__(self, other, /) -> bool:
        return (type(other) is type(self)) and (self.value == other.value)

    def __hash__(self, /) -> int:
        return hash(self.value)

    def validate(self, /) -> None:
        if type(self.value) is int:
            if self.value <= 0:
                raise ValueError("numieric UUIDs must be positive")
            return
        elif type(self.value) is str:
            if not type(self).re_valid_str.fullmatch(self.value):
                raise ValueError("invalid string uuid")
            return
        else:
            raise ValueError("Invalid value type for uuid")

    def __str__(self) -> str:
        if type(self.value) is int:
            return str(self.value)
        else:
            return "UUID" + self.value

    @classmethod
    def from_str(cls, input_str: str, /) -> UUID:
        if input_str.startswith(prefix='UUID'):
            return cls(input_str[4:])
        else:
            return cls(int(input_str))


def to_UUID_recursive(target, /):
    if target is None:
        return None
    elif type(target) is bool:
        return target
    elif type(target) is str:
        return UUID(target)
    elif type(target) is int:
        return UUID(target)
    elif type(target) is list:
        return [to_UUID_recursive(t) for t in target]
    elif type(target) is dict:
        return {k: to_UUID_recursive(v) for (k, v) in target.items()}
    elif type(target) is UUID:
        return target
    raise ValueError("Invalid input to to_UUID_recursive")


def UUID_to_JSONable_recursive(target, /):
    if type(target) is UUID:
        return target.value
    elif type(target) is list:
        return [UUID_to_JSONable_recursive(t) for t in target]
    elif type(target) is dict:
        return {k: UUID_to_JSONable_recursive(v) for (k, v) in target.items()}
    else:
        #  We basically assert that target is int, str, bool or None. We do not check here, though.
        return target


# Note that in spite of inheritance, all instances t of clases derived from (classes derived from) TypedDict have type
# (plain!) dict
# These classes serves 2 separate purposes:
# 1.) They are used as an intermediate step for (de)serializing manager instructions describe managers that are part of
#     an existing configuration of a char. In this case, all fields are actually set.
# 2.) It is used to describe managers' parameters for initial setup.
#     In this case, args, kwargs, uuid and uuid_refs may be unset.
#     args and kwargs are set when transforming to ManagerInstruction (not the _Dict).
#     uuid and uuid_refs are set upon initializing an actual manager with there parameters.
#     Due to appropriate hooks in CharVersionConfig / BaseCVManager, these hooks are guaranteed to be called before
#     ManagerInstructionBase_Dict -> JSON -> Save to database.
class ManagerInstruction_BaseDict(TypedDict):
    type_id: str
    module: str
    group: Union[str, ManagerInstructionGroups]  # key to ManagerInstructionsGroup or ManagerInstructionGroup itself.


class ManagerInstruction_Dict(ManagerInstruction_BaseDict, total=False):
    args: list
    kwargs: Dict[str, Any]
    # an unique id that is unique among objects belonging to a single given config and should not be changed later
    # (except possibly through a designated interface that globally affects a whole config)
    # Not present means unset: We set the id automatically when creating a config with such a manager.
    # uuids must be positive numbers or match re_uuid_str.
    uuid: Union[UUID, UUID_Source]
    # Any referenced uuids (including uuids of data sources / LaTeX output that are produced by the constructed mananager)
    # needs to be serialized. This should go into uuid_refs rather than into args/kwargs. Any number or string literal that
    # is (recursively!) contained, except dict keys, in uuid_refs is interpreted as a uuid and transformed into the UUID class.
    # No need to include self['uuid'].
    uuid_refs: Any


# Same as above, but is guaranteed that all keys are present and everything is in serialized format. (type(group) is str)
class ManagerInstruction_SerializedDict(ManagerInstruction_BaseDict):
    args: list
    kwargs: Dict[str, Any]
    # an unique id that is unique among objects belonging to a single given config and is not changed later.
    # Not present means unset: We set the id automatically when creating a config with such a manager.
    uuid: UUID_Source
    uuid_refs: Any


# Actual python object that we work with. Note that group is transformed str -> ManagerInstructionGroups
# uuid and uuif_refs contain UUID objects
# uuid being None means unset. This prevents calling as_dict
@dataclasses.dataclass
class ManagerInstruction:
    type_id: str
    module: str
    group: ManagerInstructionGroups
    args: list = dataclasses.field(default_factory=list)
    kwargs: dict = dataclasses.field(default_factory=dict)
    uuid: UUID = None
    uuid_refs: Any = None

    @classmethod
    def from_dict(cls, d: ManagerInstruction_Dict, /) -> ManagerInstruction:
        ret: ManagerInstruction = cls(**d)
        if type(ret.group) is not ManagerInstructionGroups:
            ret.group = ManagerInstructionGroups[d['group']]
        if ret.uuid and (type(ret.uuid) is not UUID):
            ret.uuid = UUID(d['uuid'])
        ret.uuid_refs = to_UUID_recursive(ret.uuid_refs)
        return ret

    @classmethod
    def from_serialized_dict(cls, d: ManagerInstruction_SerializedDict, /) -> ManagerInstruction:
        return cls(type_id=d['type_id'], module=d['module'], group=ManagerInstructionGroups[d['group']], args=d['args'],
                   kwargs=d['kwargs'], uuid=UUID(d['uuid']), uuid_refs=to_UUID_recursive(d['uuid_refs']))

    def as_dict(self, /) -> ManagerInstruction_SerializedDict:
        assert self.uuid
        ret: ManagerInstruction_SerializedDict = {'type_id': self.type_id, 'module': self.module, 'args': self.args,
                                                  'kwargs': self.kwargs, 'group': self.group.name, 'uuid': self.uuid.value,
                                                  'uuid_refs': UUID_to_JSONable_recursive(self.uuid_refs)}
        return ret


class PythonConfigRecipe_Dict(TypedDict):
    edit_mode: Union[int, EditModes]  # key to EditModes
    data_source_order: List[Union[UUID_Source, UUID]]
    manager_instructions: Union[Dict[Union[UUID_Source, UUID], ManagerInstruction_Dict],
                                List[ManagerInstruction_Dict]]
    last_uuid: int


class PythonConfigRecipe_SerializedDict(TypedDict):
    edit_mode: int
    data_source_order: List[UUID_Source]
    manager_instructions: Dict[UUID_Source, ManagerInstruction_SerializedDict]
    last_uuid: int


@dataclasses.dataclass
class PythonConfigRecipe:
    edit_mode: EditModes
    data_source_order: List[UUID]
    manager_instructions: Dict[UUID, ManagerInstruction]
    last_uuid: int

    @classmethod
    def from_dict(cls, d: PythonConfigRecipe_Dict, /) -> PythonConfigRecipe:
        #  Construct partial return object without manager_instruction first.
        #  We use it in case we need to assign fresh uuids.
        ret: PythonConfigRecipe = cls(edit_mode=EditModes(d['edit_mode']), data_source_order=to_UUID_recursive(d['data_source_order']),
                                      manager_instructions={}, last_uuid=d['last_uuid'])
        if type(mi := d['manager_instructions']) is dict:
            mi_new: Dict[UUID, ManagerInstruction] = {UUID(k): ManagerInstruction.from_dict(v) for (k, v) in mi.items()}
        else:
            ml: List[ManagerInstruction_Dict] = d['manager_instructions']
            assert type(ml) is list
            mi_new: Dict[UUID, ManagerInstruction] = {(UUID(x['uuid']) if 'uuid' in x else ret.take_uuid()): ManagerInstruction.from_dict(x) for x in ml}
        for k in mi_new:
            mi_new[k].uuid = k
        ret.manager_instructions = mi_new
        return ret

    @classmethod
    def from_serialized_dict(cls, d: PythonConfigRecipe_SerializedDict, /) -> PythonConfigRecipe:
        return cls(edit_mode=EditModes(d['edit_mode']), data_source_order=[UUID(x) for x in d['data_source_order']],
                   manager_instructions={UUID(k): ManagerInstruction.from_serialized_dict(v) for (k, v) in d['manager_instructions'].items()},
                   last_uuid=d['last_uuid'])

    def take_uuid(self) -> UUID:
        self.last_uuid += 1
        return UUID(self.last_uuid)

    def as_dict(self, /) -> PythonConfigRecipe_SerializedDict:
        return {'edit_mode': self.edit_mode.value,
                'data_source_order': [x.value for x in self.data_source_order],
                'manager_instructions': {k.value: v.as_dict for (k, v) in self.manager_instructions},
                'last_uuid': self.last_uuid}

    #  Removed in favor of copy.deepcopy being applied at the call site.
    #  def make_shallow_copy(self, /) -> PythonConfigRecipe:
    #        return dataclasses.replace(self)


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
                raise ValueError("Invalid Config: non-string dict key")
            validate_strict_JSON_serializability(value)
        return
    else:
        raise ValueError("Invalid Config: Contains non-allowed python type")


EMPTY_RECIPE_DICT: Final[PythonConfigRecipe_Dict] = {
    'edit_mode': EditModes.NORMAL,
    'data_source_order': [],
    'manager_instructions': [],
    'last_uuid': 1,
}
EMPTY_RECIPE: Final[PythonConfigRecipe] = PythonConfigRecipe.from_dict(EMPTY_RECIPE_DICT)


class CreateManagerEnum(IntEnum):
    no_create = 0
    create_config = 1
    destroy_config = 2
    add_manager = 3
    copy_config = 4


# Default argument for create.
NO_CREATE: Final[CreateManagerEnum] = CreateManagerEnum['no_create']
