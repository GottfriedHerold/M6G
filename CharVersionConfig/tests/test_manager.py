from __future__ import annotations
from importlib import import_module
from typing import ClassVar, Type, Optional
from copy import deepcopy

import django.test

from BackendInterface.DBCharVersion import DBCharVersion
from CharVersionConfig import BaseCVManager, EMPTY_RECIPE_DICT, PythonConfigRecipe_Dict, ManagerInstruction_Dict, ManagerInstructionGroups, PythonConfigRecipe, EditModes, ManagerInstruction, UUID, ManagerInstruction_BaseDict
from DBInterface.tests import setup_chars_and_versions, _setup_chars_and_versions_return_class
from DBInterface.models import CharVersionModel


# Test for a given manager class. Intended to be subclasses for each manager.
class BasicManagerTest(django.test.TestCase):
    cv_manager: ClassVar[Type[BaseCVManager]] = BaseCVManager
    init_users: ClassVar[bool] = True
    cvs: ClassVar[Optional[_setup_chars_and_versions_return_class]] = None
    base_recipe_dict: PythonConfigRecipe_Dict = deepcopy(EMPTY_RECIPE_DICT)
    base_recipe: PythonConfigRecipe

    char_version_backend: Type[DBCharVersion] = staticmethod(DBCharVersion)

    # Arguments to the new manager
    new_args: list = []
    new_kwargs: dict = {}
    new_uuid_refs = {}
    # These 3 get appended to the manager created by recipe_dicts. We need to postpone this to a method, because we
    # don't have cls at class scope
    base_with_new_recipe_dict: PythonConfigRecipe_Dict = deepcopy(EMPTY_RECIPE_DICT)  # modified by setUpClass
    base_with_new_recipe: PythonConfigRecipe

    # These are computed from the above:
    new_instruction_base: ManagerInstruction_BaseDict  # Base dict from cv_manager
    new_instruction_dict: ManagerInstruction_Dict  # includes new_args, new_kwargs, new_group
    # new_group_str: str

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cvs = setup_chars_and_versions()
        cls.new_instruction_base: ManagerInstruction_BaseDict = cls.cv_manager.recipe_base_dict()
        assert cls.new_instruction_base.keys() == {'type_id', 'module', 'group'}
        # Note cls.new_instruction_dict['uuid'] is missing
        cls.new_instruction_dict: ManagerInstruction_Dict = {'args': cls.new_args, 'kwargs': cls.new_kwargs,
                                                             'uuid_refs': cls.new_uuid_refs,
                                                             'group': cls.new_instruction_base['group'],
                                                             'module': cls.new_instruction_base['module'],
                                                             'type_id': cls.new_instruction_base['type_id']}
        if type(mis:=cls.base_with_new_recipe_dict['manager_instructions']) is list:
            mis.append(cls.new_instruction_dict)
        else:
            assert type(mis) is dict
            mis['new_instruction_test'] = cls.new_instruction_dict
        cls.base_with_new_recipe = PythonConfigRecipe.from_dict(cls.base_with_new_recipe_dict)
        cls.base_recipe = PythonConfigRecipe.from_dict(cls.base_recipe_dict)
        # import logging
        # logging.getLogger('chargen').critical(str(cls.base_with_new_recipe))

        cls.new_char_empty = CharVersionModel.create_root_char_version(owner=cls.cvs['char1'],
                                                                       python_config=cls.base_recipe,
                                                                       edit_mode=EditModes.EDIT_ALL_NEW)
        cls.new_char_with_manager = CharVersionModel.create_root_char_version(owner=cls.cvs['char1'], python_config=cls.base_with_new_recipe,
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

        cv_empty: DBCharVersion = self.char_version_backend(db_instance=new_char_empty, config_write_permission=True, data_write_permission=True)
        cv_with_manager: DBCharVersion = self.char_version_backend(db_instance=new_char_with_manager, config_write_permission=True, data_write_permission=True)
        cv_copy: DBCharVersion = self.char_version_backend(db_instance=new_char_copy, config_write_permission=True, data_write_permission=True)
        assert cv_empty.config_write_permission
        assert cv_with_manager.config_write_permission
        assert cv_copy.config_write_permission

        cv_empty.add_manager(ManagerInstruction.from_dict(self.new_instruction_dict))
