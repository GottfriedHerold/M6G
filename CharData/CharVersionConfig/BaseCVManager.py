from __future__ import annotations
from typing import List, ClassVar, Optional, Iterable, TYPE_CHECKING

from .CharVersionConfig import CVConfig
if TYPE_CHECKING:
    from .types import ManagerInstructions, ManagerInstructionsDictBase, ManagerInstructionsDict, PythonConfigRecipe
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
    data_source_descriptions: List[DataSourceDescription] = []
    # NOTE: Due to an __init_subclass__ hook that looks at __dict__, these do NOT get inherited to subclasses.
    module: ClassVar[str]  # Set to cls.__module__ (after class creation).
    type_id: ClassVar[str]  # Set to cls.__name__ (after class creation).

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

    def __init__(self, /, *args, cv_config: CVConfig, manager_instruction: ManagerInstructions, **kwargs):
        """
        Called by CVConfig.setup_managers() to initialize the manager
        :param cv_config: calling cv_config
        :param manager_instruction: refers to the entry in the calling cv_config's python_recipe.managers that was responsible for creating this.
        :param args: arbitrary arguments from the recipe.
        :param kwargs: arbitrary kw-arguments from the recipe.
        """
        self.args = args
        self.kwargs = kwargs
        self.cv_config = cv_config
        self.instructions = manager_instruction

    @classmethod
    def recipe_base_dict(cls, /) -> ManagerInstructionsDictBase:
        """
        This should be used in python recipes as {**CVManager.recipe_base(), ...} to set up type and module correctly.
        """
        ret: ManagerInstructionsDictBase = {'type_id': cls.type_id, 'module': cls.module}
        return ret

    def get_recipe_as_dict(self, /) -> ManagerInstructionsDict:
        """
        Used to re-create the arguments used to make this instance.
        Is almost identical to self.instructions (except that 'args' / 'kwargs' / 'type' / 'module' is always present
        and not defaulted)
        """
        return self.instructions.as_dict()

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
        target_recipe.managers.append(self.instructions.make_copy())

    def post_setup(self, /, create: bool = False) -> None:
        """
        Called after setup has finished for all managers
        """
        pass

    def get_data_sources(self, /, description: DataSourceDescription) -> Iterable[CharDataSourceBase]:
        return []

    def make_data_source(self, /, *, description: DataSourceDescription, target_list: List[CharDataSourceBase]) -> None:
        target_list.extend(self.get_data_sources(description))

    def validate_config(self, /):
        if self.instructions.module != type(self).module:
            raise ValueError("CVConfig validation failed: Registered module differs from saved module. Did you forget to create a db migration after a file rename during code reorganization?")
        if self.instructions.type_id != type(self).type_id:
            raise ValueError("CVConfig validation failed: Registered type_id differs from saved type_id. Did you forget to create a db migration after a rename of a CVManager class?")


BaseCVManager.__init_subclass__()  # BaseCVManager is a perfectly valid CVManager (that does absolutely nothing)