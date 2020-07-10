"""
This file contains basic setup routines that populate the (test) database. Intended to be used in
setUp functions from TestCase (django.test.TestCase, not unittest.TestCase)
"""

from django.db import transaction
import django.test
from DBInterface.models import CGUser, CGGroup, CharModel, CharVersionModel, CVReferencesModel
from DBInterface.models import get_default_group
from CharData.CharVersionConfig import EMPTY_RECIPE
from CharData.CharVersionConfig.EditModes import EditModes
from typing import TypedDict

class _setup_users_and_groups_return_class(TypedDict):
    """
    Return type of setup_users_and_groups. This is a class to simplify type-checking.
    """
    admin1: CGUser
    admin2: CGUser
    user1: CGUser
    user2: CGUser
    user3: CGUser
    user4: CGUser
    user5: CGUser
    test_users: CGGroup
    main_users: CGGroup
    admin_users: CGGroup
    empty_group: CGGroup
    group1: CGGroup

def setup_users_and_groups() -> _setup_users_and_groups_return_class:
    """
    Creates a bunch of test users and groups in the database.
    Returns a class that contains them.
    """
    if transaction.get_autocommit():
        raise AssertionError("Not contained in transaction")

    ret = dict()
    ret['admin1'] = admin1 = CGUser.objects.create_superuser(username='admin1', email='admin1@admins.org', password='admin1')
    ret['admin2'] = admin2 = CGUser.objects.create_superuser(username='admin2', email='admin2@admins.org', password='admin2')
    ret['user1'] = user1 = CGUser.objects.create_user(username='user1', email='user1@users.org', password='U1')
    ret['user2'] = user2 = CGUser.objects.create_user(username='user2', email='user2@users.org', password='U2')
    ret['user3'] = user3 = CGUser.objects.create_user(username='user3', email='user2@users.org', password='U2')
    ret['user4'] = user4 = CGUser.objects.create_user(username='user4', email="", password="")
    ret['user5'] = user5 = CGUser.objects.create_user(username='user5', email="", password="")

    ret['test_users'] = CGGroup.create_group('test_users', initial_users=[user1, user2, user3, user4, user5])
    ret['main_users'] = CGGroup.create_group('main_users', initial_users=[user1, user2, user3])
    ret['admin_users'] = CGGroup.create_group('admin_users', initial_users=[admin1, admin2])
    ret['empty_group'] = CGGroup.create_group('empty_group', initial_users=[])
    ret['group1'] = CGGroup.create_group('group1', initial_users=[user1])
    return ret

class _setup_chars_and_versions_return_class(_setup_users_and_groups_return_class):
    admin_char1: CharModel
    char1: CharModel
    char2: CharModel
    char3: CharModel
    char4: CharModel
    char5: CharModel
    char6: CharModel
    char7: CharModel
    cv1_1: CharVersionModel
    cv1_2: CharVersionModel
    cv1_3: CharVersionModel
    cv1_4: CharVersionModel
    cv2_1: CharVersionModel
    cv2_2: CharVersionModel

def setup_chars_and_versions() -> _setup_chars_and_versions_return_class:
    """
    Runs setup_users_and_groups, then
    creates a bunch of test chars and versions in the database.

    Returns a dict with the result of setup_users_and_groups and chars and versions.
    char1 to char5 are chars of user1 to user5
    CharVersion-Tree structure is as follows:
    cv1_1: root, NORMAL
        cv1_3: NORMAL
            cv1_4: EDIT_DATA_OVERWRITE
    cv1_2: root, EDIT_DATA_NEW
    cv2_1: root NORMAL
    cv2_2: root EDIT_DATA_NEW (derived from cv1_1)
    """
    ret: dict = setup_users_and_groups()
    ret['char1'] = char1 = CharModel.create_char(name='test_char1', creator=ret['user1'], description='TestChar1')
    ret['admin_char1'] = admin_char1 = CharModel.create_char(name='admin_char1', creator=ret['admin1'], description='AdminChar1')
    ret['char2'] = char2 = CharModel.create_char(name='test_char2', creator=ret['user2'], description='TestChar2')
    ret['char3'] = char3 = CharModel.create_char(name='test_char3', creator=ret['user3'], description='TestChar3')
    ret['char4'] = char4 = CharModel.create_char(name='test_char4', creator=ret['user4'], description='TestChar4')
    ret['char5'] = char5 = CharModel.create_char(name='test_char5', creator=ret['user5'], description='TestChar5')
    ret['char6'] = char6 = CharModel.create_char(name='test_char6', creator=ret['user1'], description='Another Char of user1')
    ret['char7'] = char7 = CharModel.create_char(name='test_char7', creator=ret['admin1'])  # no description

    ret['cv1_1'] = cv1_1 = CharVersionModel.create_root_char_version(python_config=EMPTY_RECIPE, owner=char1)
    ret['cv1_2'] = cv1_2 = CharVersionModel.create_root_char_version(python_config=EMPTY_RECIPE, owner=char1, edit_mode=EditModes.EDIT_DATA_NEW)
    ret['cv1_3'] = cv1_3 = CharVersionModel.derive_char_version(parent=cv1_1, edit_mode=EditModes.NORMAL)
    ret['cv1_4'] = cv1_4 = CharVersionModel.derive_char_version(parent=cv1_3, edit_mode=EditModes.EDIT_DATA_OVERWRITE)
    ret['cv2_1'] = cv2_1 = CharVersionModel.create_root_char_version(python_config=EMPTY_RECIPE, owner=char2)
    ret['cv2_2'] = cv2_2 = CharVersionModel.derive_char_version(parent=cv1_1, owner=char2, edit_mode=EditModes.EDIT_DATA_NEW)
    return ret

class TestUsersAndGroupSetup(django.test.TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.users_and_groups = setup_chars_and_versions()

    def test_setup_users(self):
        admin1 = CGUser.objects.get(username='admin1')
        self.assertEqual(admin1, self.users_and_groups['admin1'])
        admin2 = CGUser.objects.get(username='admin2')

        user1 = CGUser.objects.get(username='user1')
        self.assertEqual(user1, self.users_and_groups['user1'])
        user2 = CGUser.objects.get(username='user2')
        user3 = CGUser.objects.get(username='user3')
        user4 = CGUser.objects.get(username='user4')
        user5 = CGUser.objects.get(username='user5')

        all_group = get_default_group()
        test_users = CGGroup.objects.get(name='test_users')
        self.assertEqual(test_users, self.users_and_groups['test_users'])
        main_users = self.users_and_groups['main_users']
        admin_users = self.users_and_groups['admin_users']
        empty_group = CGGroup.objects.get(name='empty_group')
        self.assertEqual(empty_group, self.users_and_groups['empty_group'])
        group1 = self.users_and_groups['group1']

    def test_setup_chars(self):
        for i in range(1, 7):
            # noinspection PyTypedDict
            self.assertEqual(self.users_and_groups['char'+str(i)], CharModel.objects.get(name='test_char'+str(i)))
        cv1_1: CharVersionModel = self.users_and_groups['cv1_1']
        cv1_2: CharVersionModel = self.users_and_groups['cv1_2']
        cv1_3: CharVersionModel = self.users_and_groups['cv1_3']
        cv1_4: CharVersionModel = self.users_and_groups['cv1_4']
        cv2_1: CharVersionModel = self.users_and_groups['cv2_1']
        cv2_2: CharVersionModel = self.users_and_groups['cv2_2']

        char1s = set(CharVersionModel.objects.filter(owner=self.users_and_groups['char1']))
        char2s = set(CharVersionModel.objects.filter(owner=self.users_and_groups['char2']))
        self.assertEqual(char1s, {cv1_1, cv1_2, cv1_3, cv1_4})
        self.assertEqual(char2s, {cv2_1, cv2_2})

        assert cv1_1.edit_mode == EditModes.NORMAL
        assert cv1_2.edit_mode == EditModes.EDIT_DATA_NEW
        assert cv1_3.edit_mode == EditModes.NORMAL
        assert cv1_4.edit_mode == EditModes.EDIT_DATA_OVERWRITE
        assert cv2_1.edit_mode == EditModes.NORMAL
        assert cv2_2.edit_mode == EditModes.EDIT_DATA_NEW

        CVReferencesModel.check_reference_validity_for_char_version(cv1_1)
        CVReferencesModel.check_reference_validity_for_char_version(cv1_2)
        CVReferencesModel.check_reference_validity_for_char_version(cv1_3)
        CVReferencesModel.check_reference_validity_for_char_version(cv1_4)
        CVReferencesModel.check_reference_validity_for_char_version(cv2_1)
        CVReferencesModel.check_reference_validity_for_char_version(cv2_2)
