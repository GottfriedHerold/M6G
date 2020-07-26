"""
This file defines the BaseCVManager class, which is the base class for all CVManagers.
Every char version has a set of CVManager instances managed via CharVersionConfig.CVConfig.
Each of these managers represents a set of configuration options, determines data sources, LaTeX outputs and what
input pages to display.
BaseCVManager itself just defines the interface with some meaningful defaults. While it provides absolutely no
functionality (such as data sources etc.) by itself, it is a perfectly valid CVManager.
"""
from __future__ import annotations
from typing import List, ClassVar, Optional, Iterable, TYPE_CHECKING, Dict, Any
import copy
# from enum import IntEnum

from .CharVersionConfig import CVConfig
from .types import ManagerInstructionGroups

if TYPE_CHECKING:
    from .types import ManagerInstruction, ManagerInstruction_Dict, ManagerInstruction_BaseDict, PythonConfigRecipe, CreateManagerEnum, UUID, ManagerInstruction_SerializedDict
    from .DataSourceDescription import DataSourceDescription
    from DBInterface.models import CharVersionModel
    from DataSources import CharDataSourceBase


class BaseCVManager:
    """
    CVManager that does nothing. For testing and serves as base class.
    """

    # List of DataSourceDescriptions that is displayed to the user when this manager is present.
    # CVConfig.data_source_order is a permutation of indices into the list of all data_source_descriptions.
    # make_data_source is called for each data_source_description.
    # May be overwritten by a property.
    data_source_descriptions: Dict[UUID, DataSourceDescription] = {}

    # module and type_id are required for serialization. Due to an __init_subclass__ hook that looks at __dict__,
    # these get automatically overwritten in subclasses unless explicitly set (not recommended).
    module: ClassVar[str]  # Set to cls.__module__ (after class creation).
    type_id: ClassVar[str]  # Set to cls.__name__ (after class creation).
    uuid: UUID

    # manager_instruction is the ManagerInstruction that was used to create the instance. Note that instruction refers
    # to the instruction contained in cv_config.python_recipe by identity.
    manager_instruction: ManagerInstruction  # TODO: Weak-ref

    # managing CVConfig instance. This can be used to check the presence of other CVManagers.
    cv_config: CVConfig  # TODO: Weak-ref?

    # Called manually for BaseCVManager itself.
    def __init_subclass__(cls, module: str = None, type_id: str = None, register: bool = True, **kwargs):
        """
        Init subclass hook: When deriving subclasses class Derived(BaseCVManager, module=..., type_id=..., register=...)
        we automatically set Derived.module and Derived.type_id and register Derived. This is required for correct
        serialization.
        Setting register to False as in class AbstractManager(BaseCVManager, register=False): ...
        can be used to avoid registering AbstractManager; this should be done for abstract CVManager classes.
        """
        super().__init_subclass__(**kwargs)
        if module is not None:
            if m:=cls.__dict__.get('module') is not None:
                assert m == module
            cls.module = module
        if cls.__dict__.get('module') is None:
            cls.module = cls.__module__

        if type_id is not None:
            if t:=cls.__dict__.get('type_id') is not None:
                assert t == type_id
            cls.type_id = type_id
        if cls.__dict__.get('type_id') is None:
            cls.type_id = cls.__name__
        if register:
            CVConfig.register(type_id=cls.type_id, creator=cls)

    def __init__(self, /, *args, uuid: UUID, uuid_refs: Any, cv_config: CVConfig, manager_instruction: ManagerInstruction, **kwargs):
        """
        Called by CVConfig.setup_managers() to initialize the manager
        May be overwritten in a subclass, but you need to ensure self.manager_instruction, self.cv_config and self.uuid are set.
        :param cv_config: calling cv_config. We store a reference
        :param manager_instruction: refers to the entry in the calling cv_config's python_recipe.managers that was responsible for creating this.
        :param args: arbitrary arguments from the recipe. Prefer kwargs, as args might become deprecated.
        :param kwargs: arbitrary kw-arguments from the recipe.
        :param uuid key storing this manager in the config
        :param uuid_refs: arbitrary arguments that undergo a nested UUID serialization.
        """
        self.args = args
        self.kwargs = kwargs
        self.cv_config = cv_config
        self.manager_instruction = manager_instruction  # Important: Must not copy, but bind.
        self.uuid = uuid
        self.uuid_refs= uuid_refs

    def post_setup(self, /, create: CreateManagerEnum, **kwargs) -> None:
        """
        Normally called after __init__ has finished for all managers with create=no_create.

        create = CreateManagerEnum.no_create: normal operation as above.
        create = CreateManagerEnum.create_config: Called once at creation of the owning config. Might need to do database setup.
        create = CreateManagerEnum.destroy_config: Called once at destruction of owning config. Might need to do database cleanup.
        create = CreateManagerEnum.add_manager: Called once upon adding this manager to the owning config.
        create = CreateManagerEnum.copy_config: Called on target when copying.
                 kwargs = {transplant: bool, old_config: CVConfig}

        See Notes.txt for precise non-obvious usage.
        """
        assert (not kwargs) or (create is CreateManagerEnum.copy_config)

    @classmethod
    def recipe_base_dict(cls, /) -> ManagerInstruction_BaseDict:
        """
        This should be used in python recipes as {**CVManager.recipe_base(), ...} to set up type and module correctly.
        No need to overwrite.
        """
        ret: ManagerInstruction_BaseDict = {'type_id': cls.type_id, 'module': cls.module, 'group': ManagerInstructionGroups('default')}
        return ret

    def get_recipe_as_dict(self, /) -> ManagerInstruction_SerializedDict:
        """
        Used to re-create the arguments used to make this instance. No need to overwrite.
        """
        return self.manager_instruction.as_dict()

    # TODO!!!
    # noinspection PyUnusedLocal
    def copy_config(self, target_recipe: PythonConfigRecipe, /, *, transplant: bool, target_db: Optional[CharVersionModel]) -> None:
        """
        Called for each manager on the source CharVersion when the containing CharVersion is copied.
        target_recipe is the python recipe for the new char with (new!) edit_mode and data_source_order already set.
        Its target_recipe.managers is initally empty.
        CVManager.copy_config is responsible for creating the corresponding entry in the target_recipe.
        transplant indicates whether we copy to a new CharModel
        target_db is the db entry of the new_char.

        Make sure to insert a (possibly modified) deep copy of the instruction. While a shallow copy might
        work as long as we never mutate any existing ManagerInstruction, deep copying is safer.

        self.cv_config.post_process_copy_config is a deque of callables(new_py_recipe) that is called after all
        copy_configs are run.

        Both copy_config and the the deque's callables modify its target_recipe argument.
        """
        target_recipe.manager_instructions.append(copy.deepcopy(self.manager_instruction))

    def delete_manager(self):
        """Called before the manager is deleted from a config."""
        pass

    def change_instruction(self, new_instruction: ManagerInstruction, python_recipe: PythonConfigRecipe, /) -> None:
        """
        Called when the instructions of the manager change to new_instructions.
        May in some cases need to modify python_recipe (which is the owning config's recipe).
        CHANGED!
        Note that the actual modification of instructions is done by the caller afterwards.

        See Notes.txt for precise usage requirements.
        """
        assert self.uuid == new_instruction.uuid
        python_recipe.manager_instructions[self.uuid] = new_instruction


    def _get_data_sources(self, /, description: DataSourceDescription) -> Iterable[CharDataSourceBase]:
        return []

    def make_data_source(self, /, *, description: DataSourceDescription, target_list: List[CharDataSourceBase]) -> None:
        target_list.extend(self._get_data_sources(description))

    def validate_config(self, /):
        if self.manager_instruction.module != type(self).module:
            raise ValueError("CVConfig validation failed: Registered module differs from saved module. Did you forget to create a db migration after a file rename during code reorganization?")
        if self.manager_instruction.type_id != type(self).type_id:
            raise ValueError("CVConfig validation failed: Registered type_id differs from saved type_id. Did you forget to create a db migration after a rename of a CVManager class?")


# BaseCVManager is actually a perfectly valid CVManager (that does absolutely nothing) itself.
# This is required to make it usable:
BaseCVManager.__init_subclass__()
