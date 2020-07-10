from django.db import transaction
import django.test
from DBInterface.models import CharModel, CharVersionModel
from CharData.CharVersionConfig import EMPTY_RECIPE

from .test_setup import setup_chars_and_versions

class TestChars(django.test.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cvs = setup_chars_and_versions()

    def test_tree_validator(self):
        char1: CharModel = self.cvs['char1']
        char2: CharModel = self.cvs['char2']
        char1.validate_treeness()
        char2.validate_treeness()

        with self.assertRaises(BaseException):
            with transaction.atomic():
                cv: CharVersionModel = self.cvs['cv1_1']
                cv.parent = cv
                cv.save()
                char1.validate_treeness()
        with self.assertRaises(BaseException):
            with transaction.atomic():
                cv1: CharVersionModel = self.cvs['cv1_1']
                cv4: CharVersionModel = self.cvs['cv1_4']
                cv1.parent = cv4
                cv1.save()
                char1.validate_treeness()

class TestCharVersions(django.test.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cvs = setup_chars_and_versions()

    def test_name(self):
        cv1: CharModel = self.cvs['char1']
        assert cv1.name == 'test_char1'
        cv1_1: CharVersionModel = self.cvs['cv1_1']
        assert cv1_1.name == 'test_char1'
        cv = CharVersionModel.create_root_char_version(owner=cv1, version_name='another test', python_config=EMPTY_RECIPE)
        assert cv.name == 'another test'

    def test_dummy(self):
        cv1 = CharVersionModel.make_dummy(10)
        cv2 = CharVersionModel.make_dummy(1)
        with self.assertRaises(BaseException):
            with transaction.atomic():
                cv1.save()
        with self.assertRaises(BaseException):
            with transaction.atomic():
                cv2.save()

        cv1_1 = self.cvs['cv1_1']
        fake_cv1_1 = CharVersionModel.make_dummy(cv1_1.pk)
        cvs1 = set(CharVersionModel.objects.filter(parent=cv1_1))
        cvs2 = set(CharVersionModel.objects.filter(parent=fake_cv1_1))
        self.assertEqual(cvs1, cvs2)
