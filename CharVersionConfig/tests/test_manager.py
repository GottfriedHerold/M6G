from __future__ import annotations
from importlib import import_module
from typing import ClassVar, Type, Optional
from copy import deepcopy
from BackendInterface.DBCharVersion import DBCharVersion

import django.test

from CharVersionConfig import BaseCVManager, EMPTY_RECIPE_DICT, PythonConfigRecipeDict, ManagerInstructionDict, ManagerInstructionDictBase, ManagerInstructionGroups, PythonConfigRecipe, EditModes, ManagerInstruction
from DBInterface.tests import setup_chars_and_versions, _setup_chars_and_versions_return_class
from DBInterface.models import CharVersionModel


class BasicManagerTest(django.test.TestCase):
    cv_manager: ClassVar[Type[BaseCVManager]] = BaseCVManager
    init_users: ClassVar[bool] = True
    cvs: ClassVar[Optional[_setup_chars_and_versions_return_class]] = None
    empty_recipe_dict: PythonConfigRecipeDict = deepcopy(EMPTY_RECIPE_DICT)

    char_version_backend: Type[DBCharVersion] = staticmethod(DBCharVersion)

    # Arguments to the new manager
    new_args: list = []
    new_kwargs: dict = {}
    new_group: ClassVar[ManagerInstructionGroups] = ManagerInstructionGroups.default
    # These 3 get appended to the manager created by recipe_dicts
    recipe_dict: PythonConfigRecipeDict = deepcopy(EMPTY_RECIPE_DICT)  # modified by setUpClass

    # These are compute from the above:
    new_instruction_base: ManagerInstructionDictBase  # Base dict from cv_manager
    new_instruction_dict: ManagerInstructionDict  # includes new_args, new_kwargs, new_group
    new_group_str: str



    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cvs = setup_chars_and_versions()
        cls.new_instruction_base: ManagerInstructionDictBase = cls.cv_manager.recipe_base_dict()
        assert cls.new_instruction_base.keys() == {'type_id', 'module'}
        cls.new_group_str = cls.new_group.name
        cls.new_instruction_dict: ManagerInstructionDict = {'args': cls.new_args, 'kwargs': cls.new_kwargs,
                                                          'group': cls.new_group_str, 'module': cls.new_instruction_base['module'],
                                                          'type_id': cls.new_instruction_base['type_id']}
        cls.recipe_dict['manager_instructions'].append(cls.new_instruction_dict)
        cls.new_char_empty = CharVersionModel.create_root_char_version(owner=cls.cvs['char1'],
                                                                       python_config=PythonConfigRecipe.from_nested_dict(**cls.empty_recipe_dict),
                                                                       edit_mode=EditModes.EDIT_ALL_NEW)
        cls.new_char_with_manager = CharVersionModel.create_root_char_version(owner=cls.cvs['char1'], python_config=PythonConfigRecipe.from_nested_dict(**cls.recipe_dict),
                                                                              edit_mode=EditModes.EDIT_ALL_NEW)
        cls.new_char_copy = CharVersionModel.derive_char_version(parent=cls.new_char_with_manager)

    def setUp(self):
        super().setUp()

    def test_import(self):
        import_module(self.cv_manager.module)

    def test_setup(self):
        pass

    def test_manager(self):
        new_char_empty = self.new_char_empty
        new_char_with_manager = self.new_char_with_manager
        new_char_copy = self.new_char_copy

        cv_empty = self.char_version_backend(db_instance=new_char_empty, config_write_permission=True, data_write_permission=True)
        cv_with_manager = self.char_version_backend(db_instance=new_char_with_manager, config_write_permission=True, data_write_permission=True)
        cv_copy = self.char_version_backend(db_instance=new_char_copy, config_write_permission=True, data_write_permission=True)
        assert cv_empty.config_write_permission
        assert cv_with_manager.config_write_permission
        assert cv_copy.config_write_permission

        cv_empty.add_manager(ManagerInstruction.from_nested_dict(**self.new_instruction_dict))

