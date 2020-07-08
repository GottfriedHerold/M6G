import unittest
from CharData import Regexps

class TestRegexps(unittest.TestCase):

    def test_re_key_regular(self):
        re_key = Regexps.re_key_regular
        self.assertTrue(re_key.fullmatch("a_b_c"))
        self.assertIsNone(re_key.fullmatch(""))
        self.assertFalse(re_key.fullmatch(".a"))
        self.assertFalse(re_key.fullmatch("."))
        self.assertFalse(re_key.fullmatch("a."))
        self.assertTrue(re_key.fullmatch("_a_._b_._c_d_"))
        self.assertFalse(re_key.fullmatch("__a.b"))
        self.assertFalse(re_key.fullmatch("a__.b"))
        self.assertFalse(re_key.fullmatch("a.__b"))
        self.assertFalse(re_key.fullmatch("a.b__"))
        self.assertTrue(re_key.fullmatch("a__b._c__d_"))
        self.assertFalse(re_key.fullmatch("_a_.._b_"))
        self.assertFalse(re_key.fullmatch("AaZz_.AaZzCc_"))
        self.assertFalse(re_key.fullmatch("a;b"))

    def test_re_key_any(self):
        re_key = Regexps.re_key_any
        self.assertTrue(re_key.fullmatch("a_b_c"))
        self.assertIsNone(re_key.fullmatch(""))
        self.assertFalse(re_key.fullmatch(".a"))
        self.assertFalse(re_key.fullmatch("."))
        self.assertFalse(re_key.fullmatch("a."))
        self.assertTrue(re_key.fullmatch("_a_._b_._c_d_"))
        self.assertTrue(re_key.fullmatch("__a.b"))
        self.assertTrue(re_key.fullmatch("a__.b"))
        self.assertTrue(re_key.fullmatch("a.__b"))
        self.assertTrue(re_key.fullmatch("a.b__"))
        self.assertTrue(re_key.fullmatch("a__b._c__d_"))
        self.assertFalse(re_key.fullmatch("_a_.._b_"))
        self.assertFalse(re_key.fullmatch("AaZz_.AaZzCc_"))
        self.assertFalse(re_key.fullmatch("a;b"))

    def test_re_key_restrict(self):
        re_key = Regexps.re_key_restrict
        self.assertFalse(re_key.fullmatch("a_b_c"))
        self.assertIsNone(re_key.fullmatch(""))
        self.assertFalse(re_key.fullmatch(".a"))
        self.assertFalse(re_key.fullmatch("."))
        self.assertFalse(re_key.fullmatch("a."))
        self.assertFalse(re_key.fullmatch("_a_._b_._c_d_"))
        self.assertTrue(re_key.fullmatch("__a.b"))
        self.assertTrue(re_key.fullmatch("a__.b"))
        self.assertTrue(re_key.fullmatch("a.__b"))
        self.assertTrue(re_key.fullmatch("a.b__"))
        self.assertFalse(re_key.fullmatch("a__b._c__d_"))
        self.assertFalse(re_key.fullmatch("_a_.._b_"))
        self.assertFalse(re_key.fullmatch("AaZz_.AaZzCc_"))
        self.assertFalse(re_key.fullmatch("__A__"))
        self.assertFalse(re_key.fullmatch("a;b"))
        self.assertTrue(re_key.fullmatch("__a__"))
        self.assertTrue(re_key.fullmatch("__a__.__b__.__c__"))
        self.assertTrue(re_key.fullmatch("a.__b__.c.__d__.e"))
        self.assertTrue(re_key.fullmatch("a__.b.c.__def__g"))

        match = re_key.fullmatch("__a__.b.__c.d")
        self.assertEqual(match.group('head'), "__a__.b.__c")
        self.assertEqual(match.group('restrict'), "__c")
        self.assertEqual(match.group('tail'), ".d")

        match = re_key.fullmatch("___a___")
        self.assertEqual(match.group('head'), match.group('restrict'))
        self.assertEqual(match.group('head'), "___a___")
        self.assertEqual(match.group('tail'), "")
