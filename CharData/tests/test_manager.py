from __future__ import annotations
from importlib import import_module
from typing import ClassVar, Type, Optional, Final
from copy import deepcopy

import django.test

from CharData.CharVersionConfig import BaseCVManager, CVConfig, EMPTY_RECIPE_DICT, PythonConfigRecipeDict, ManagerInstructionDict, ManagerInstructionDictBase, ManagerInstructionGroups, PythonConfigRecipe, EditModes
from DBInterface.tests import setup_users_and_groups, _setup_users_and_groups_return_class, setup_chars_and_versions, _setup_chars_and_versions_return_class
from DBInterface.models import CharVersionModel


class BasicManagerTest(django.test.TestCase):
    cv_manager: ClassVar[Type[BaseCVManager]] = BaseCVManager
    init_users: ClassVar[bool] = True
    cvs: ClassVar[Optional[_setup_chars_and_versions_return_class]] = None
    empty_recipe_dict: PythonConfigRecipeDict = deepcopy(EMPTY_RECIPE_DICT)

    new_args: list = []
    new_kwargs: dict = {}
    new_group: ClassVar[ManagerInstructionGroups] = ManagerInstructionGroups.default
    # These 3 get appended to the manager created by recipe_dicts
    recipe_dict: PythonConfigRecipeDict = deepcopy(EMPTY_RECIPE_DICT)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cvs = setup_chars_and_versions()
        new_instructions_base: ManagerInstructionDictBase = cls.cv_manager.recipe_base_dict()
        assert new_instructions_base.keys() == {'type_id', 'module'}
        group_str: str = cls.new_group.name
        new_instructions_dict: ManagerInstructionDict = {'args': cls.new_args, 'kwargs': cls.new_kwargs,
                                                          'group': group_str, 'module': new_instructions_base['module'],
                                                          'type_id': new_instructions_base['type_id']}
        cls.recipe_dict['managers'].append(new_instructions_dict)
        cls.new_char_empty = CharVersionModel.create_root_char_version(owner=cls.cvs['char1'],
                                                                       python_config=PythonConfigRecipe.from_nested_dict(**cls.empty_recipe_dict),
                                                                       edit_mode=EditModes.NORMAL)
        cls.new_char_with_manager = CharVersionModel.create_root_char_version(owner=cls.cvs['char1'], python_config=PythonConfigRecipe.from_nested_dict(**cls.recipe_dict),
                                                                              edit_mode=EditModes.NORMAL)
        cls.new_char_copy = CharVersionModel.derive_char_version(parent=cls.new_char_with_manager)


    def setUp(self):
        super().setUp()

    def test_import(self):
        import_module(self.cv_manager.module)

    def test_setup(self):
        pass