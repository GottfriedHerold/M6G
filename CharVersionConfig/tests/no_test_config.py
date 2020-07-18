from django.test import TestCase
from copy import deepcopy
from DBInterface.models import CGUser, CharModel, CharVersionModel
from BackendInterface.DBCharVersion import DBCharVersion

class CVManagerTest(TestCase):

    type_string = 'base'
    base_config = {
        'edit_mode': False,
        'defaults': [
            {'type': 'NaiveDB'}
        ]
    }

    target_sub_recipe = None
    new_entry = {}
    target_type = None

    @classmethod
    def make_default_config(cls, target_sub_recipe: str = None, new_entry: dict = None) -> dict:
        if new_entry is None:
            new_entry = {}
        new_recipe: dict = deepcopy(cls.base_config)
        if target_sub_recipe:
            new_recipe[target_sub_recipe].append(new_entry)
        return new_recipe

    @property
    def default_config(self):
        return self.make_default_config(target_sub_recipe=self.target_sub_recipe, new_entry=self.new_entry)



    def setUp(self):
        self.user1 = CGUser.objects.create_user(username='user1', email='user1@users.org', password='U1')
        self.char1 = CharModel.create_char(name='TestChar1', creator=self.user1)
        self.char1_1 = CharVersionModel.create_char_version(python_config=self.default_config, owner=self.char1)
        self.char1_2 = CharVersionModel.create_char_version(parent=self.char1_1)
        self.char1_3 = CharVersionModel.create_char_version(parent=self.char1_2, edit_mode=True)

    def test_config(self):
        cv1 = DBCharVersion(db_instance=self.char1_1)
        cv1.set_input(key='a.b', value='=1+b.c', target_type=self.target_type)
        cv1.set_input(key='b.c', value='10', target_type=self.target_type)
        r = cv1.get('a.b')
        self.assertEqual(r, 11)
        char2 = CharVersionModel.create_char_version(parent=self.char1_1)
        cv2 = DBCharVersion(db_instance=char2)
        cv2.set_input(key='a.b', value='=2*b.c', target_type=self.target_type)
        cv1.set_input(key='b.c', value='6', target_type=self.target_type)
        self.assertEqual(cv2.get('a.b'), 20)
        self.assertEqual(cv1.get('a.b'), 7)
