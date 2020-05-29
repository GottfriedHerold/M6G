from django.test import TestCase
from .models import CGUser, CGGroup, CharVersionModel, CharModel, UserPermissionsForChar, GroupPermissionsForChar, get_default_group, CharUsers

# Create your tests here.

class UserAndCharManagement(TestCase):
    def setUp(self):
        self.admin = CGUser.objects.create_superuser(username='admin', email='admin@admin.org', password='admin')
        self.user1 = CGUser.objects.create_user(username='user1', email='user1@users.org', password='U1')
        self.user2 = CGUser.objects.create_user(username='user2', email='user2@users.org', password='U2')
        self.user3 = CGUser.objects.create_user(username='user3', email='user2@users.org', password='U2')
        self.user_group = CGGroup.create_group('test_users', initial_users=[self.user1, self.user2, self.user3])
        self.char1 = CharModel.create_char(name='TestChar1', creator=self.admin)
        self.char1_1 = self.char1.create_char_version()
        self.char1_2 = self.char1.create_char_version(parent=self.char1_1, version_name='second version')
        self.char2 = CharModel.create_char(name='TestChar2', creator=self.user1)
        self.char2_1 = CharVersionModel.create_char_version(owner=self.char2, description='Second char, initial version')
        self.char3 = CharModel.create_char(name='TestChar3', creator=self.user1)
        self.char3_1 = self.char3.create_char_version(parent=self.char1_2)

    def test_setup(self):
        user1 = CGUser.objects.get(username='user1')
        user2 = CGUser.objects.get(username='user2')
        user3 = CGUser.objects.get(username='user3')
        all_group = get_default_group()
        user_group = CGGroup.objects.get(name='test_users')
        char1 = CharModel.objects.get(name='TestChar1')
        char2 = CharModel.objects.get(name='TestChar2')
        char3 = CharModel.objects.get(name='TestChar3')
        char1_1 = CharVersionModel.objects.get(parent__isnull=True, owner=char1)
        char1_2 = CharVersionModel.objects.get(parent=char1_1, owner=char1)
        char2_1 = CharVersionModel.objects.get(parent=None, owner=char2)
        char3_1 = CharVersionModel.objects.get(parent=None, owner=char3)

