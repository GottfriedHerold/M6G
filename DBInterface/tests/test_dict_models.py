from .test_setup import setup_chars_and_versions
import django.test
from DBInterface.models import DictEntry, LongDictEntry, ShortDictEntry, SimpleDBToDict, CharVersionModel

class TestDictEntry(django.test.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cvs = setup_chars_and_versions()

    def test_DBDictWrapper(self):
        cv1_1 = self.cvs['cv1_1']
        cv1_2 = self.cvs['cv1_2']
        dict_like1 = SimpleDBToDict(manager=ShortDictEntry.objects, char_version_model=cv1_1)
        dict_like2 = ShortDictEntry.as_dict_for(cv1_2)
        dict_like_long = LongDictEntry.as_dict_for(cv1_1)

        ShortDictEntry.objects.create(char_version=cv1_2, key='x', value='y')
        self.assertEqual(len(dict_like1), 0)
        dict_like1['abc'] = '1'
        dict_like1['cde'] = '5'
        self.assertEqual(len(dict_like1), 2)
        del dict_like1['cde']
        self.assertTrue('abc' in dict_like1)
        self.assertFalse('cde' in dict_like1)
        dict_like1['abc'] = '6'
        self.assertEqual(len(dict_like1), 1)
        self.assertEqual(dict_like1['abc'], '6')
        dict_like2['xx'] = 'yy'
        d = dict(dict_like2.items())
        self.assertEqual(d, {'xx': 'yy', 'x': 'y'})
