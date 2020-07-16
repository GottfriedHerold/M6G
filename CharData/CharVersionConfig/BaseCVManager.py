from __future__ import annotations
from typing import List, ClassVar, Optional, Iterable, TYPE_CHECKING
# from enum import IntEnum

from .CharVersionConfig import CVConfig
# from .types import NO_CREATE
if TYPE_CHECKING:
    from .types import ManagerInstruction, ManagerInstructionDictBase, ManagerInstructionDict, PythonConfigRecipe, CreateManagerEnum
    from .DataSourceDescription import DataSourceDescription
    from DBInterface.models import CharVersionModel
    from CharData.DataSources import CharDataSourceBase


class BaseCVManager:
    """
    Manager that does nothing. For testing and serves as base class.
    """

    # List of DataSourceDescriptions that is displayed to the user when this manager is present.
    # CVConfig.data_source_order is a permutation of indices into the list of all data_source_descriptions.
    # make_data_source is called for each data_source_description.
    # May be overwritten by a property.
    data_source_descriptions: List[DataSourceDescription] = []

    # NOTE: Due to an __init_subclass__ hook that looks at __dict__, these get automatically overwritten in subclasses unless explicitly set (not recommended).
    module: ClassVar[str]  # Set to cls.__module__ (after class creation).
    type_id: ClassVar[str]  # Set to cls.__name__ (after class creation).
    instruction: ManagerInstruction
    cv_config: CVConfig

    # Called manually for BaseCVManager itself.
    def __init_subclass__(cls, module: str = None, type_id: str = None, register: bool = True, **kwargs):
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

    def __init__(self, /, *args, cv_config: CVConfig, manager_instruction: ManagerInstruction, **kwargs):
        """
        Called by CVConfig.setup_managers() to initialize the manager
        May be overwritten in a subclass, but you need to ensure self.instruction and self.cv_config are set.
        :param cv_config: calling cv_config
        :param manager_instruction: refers to the entry in the calling cv_config's python_recipe.managers that was responsible for creating this.
        :param args: arbitrary arguments from the recipe.
        :param kwargs: arbitrary kw-arguments from the recipe.
        """
        self.args = args
        self.kwargs = kwargs
        self.cv_config = cv_config
        self.instruction = manager_instruction  # Important: Must not copy, but bind.

    def post_setup(self, /, create: CreateManagerEnum) -> None:
        """
        Normally called after __init__ has finished for all managers with create=no_create.

        create = CreateManagerEnum.no_create: normal operation as above.
        create = CreateManagerEnum.create_config: Called once at creation of the owning config. Might need to do database setup.
        create = CreateManagerEnum.destroy_config: Called once at destruction of owning config. Might need to do database cleanup.
        create = CreateManagerEnum.add_manager: Called once upon adding this manager to the owning config.

        See Notes.txt for precise non-obvious usage.
        """
        pass


    @classmethod
    def recipe_base_dict(cls, /) -> ManagerInstructionDictBase:
        """
        This should be used in python recipes as {**CVManager.recipe_base(), ...} to set up type and module correctly.
        No need to overwrite.
        """
        ret: ManagerInstructionDictBase = {'type_id': cls.type_id, 'module': cls.module}
        return ret

    def get_recipe_as_dict(self, /) -> ManagerInstructionDict:
        """
        Used to re-create the arguments used to make this instance. No need to overwrite.
        """
        return self.instruction.as_dict()

    def copy_config(self, target_recipe: PythonConfigRecipe, /, *, transplant: bool, target_db: Optional[CharVersionModel]) -> None:
        """
        Called for each manager on the source CharVersion when the containing CharVersion is copied.
        target_recipe is the python recipe for the new char with (new!) edit_mode and data_source_order already set.
        Its target_recipe.managers is initally empty.
        CVManager.copy_config is responsible for creating the corresponding entry in the target_recipe.
        transplant indicates whether we copy to a new CharModel
        target_db is the db entry of the new_char.

        self.cv_config.post_process_copy_config is a deque of callables(new_py_recipe) that is called after all
        copy_configs are run.

        Both copy_config and the the deque's callables modify its target_recipe argument.
        """
        target_recipe.manager_instructions.append(self.instruction.make_copy())

    def delete_manager(self):
        """Called before the manager is deleted from a config."""
        pass

    def change_instruction(self, new_instruction: ManagerInstruction, python_recipe: PythonConfigRecipe, /) -> None:
        """
        Called when the instructions of the manager change to new_instructions.
        May in some cases need to modify python_recipe (which is the owning config's recipe).
        Note that the actual modification of instructions is done by the caller afterwards.

        See Notes.txt for precise usage requirements.
        """
        pass

    def _get_data_sources(self, /, description: DataSourceDescription) -> Iterable[CharDataSourceBase]:
        return []

    def make_data_source(self, /, *, description: DataSourceDescription, target_list: List[CharDataSourceBase]) -> None:
        target_list.extend(self._get_data_sources(description))

    def validate_config(self, /):
        if self.instruction.module != type(self).module:
            raise ValueError("CVConfig validation failed: Registered module differs from saved module. Did you forget to create a db migration after a file rename during code reorganization?")
        if self.instruction.type_id != type(self).type_id:
            raise ValueError("CVConfig validation failed: Registered type_id differs from saved type_id. Did you forget to create a db migration after a rename of a CVManager class?")


# BaseCVManager is actually a perfectly valid CVManager (that does absolutely nothing) itself. This is required to make it usable:
BaseCVManager.__init_subclass__()
