from CharData import Parser
from CharData import BaseCharVersion
from CharData import CharExceptions
import unittest


class TestParser(unittest.TestCase):
    p = Parser.parser.parse

    @staticmethod
    def ev(term):
        return term.eval_ast(None, {})

    @classmethod
    def evp(cls, s: str):
        return cls.ev(cls.p(s))

    def test_rules(self):
        for sa in Parser.special_args.values():
            assert sa[0] in Parser.tokens
        assert Parser.CONTINUE_LOOKUP not in Parser.special_args
        for keyword in Parser.keywords:
            assert keyword == keyword.upper()

    def test_add(self):
        t = self.p("1 + 5")
        assert self.ev(t) == 6

    def test_sub(self):
        assert self.evp("2 - 6") == -4

    def test_true(self):
        assert self.evp("TRUE")

    def test_false(self):
        assert not self.evp("FALSE")

    def test_string_lit(self):
        assert self.evp("'a1b' + 'X' + 'Y' * 3 + 'Z'") == 'a1bXYYYZ'

    def test_float(self):
        t = self.p("1.5 + 2.5")
        assert self.ev(t) == 4.0

    def test_proddiv(self):
        t = self.p("4*5+9/2")
        assert self.ev(t) == 24.5

    def test_idiv(self):
        t = self.p("9//2")
        assert self.ev(t) == 4

    def test_bracket(self):
        t = self.p(" ((4+5)*3) ")
        assert self.ev(t) == 27

    # noinspection PyProtectedMember
    def test_variable(self):
        old = Parser._ALLOWED_SPECIAL_ARGS
        try:
            Parser._ALLOWED_SPECIAL_ARGS |= {'test_var'}
            t = self.p("$test_var + 4")
            assert t.eval_ast(None, {'test_var': 7}) == 11
        finally:
            Parser._ALLOWED_SPECIAL_ARGS = old

        with self.assertRaises(Parser.CGParseException):
            self.p("$test_var + 4")

    def test_equality(self):
        t = self.p("4 == 5")
        assert self.ev(t) is False
        t = self.p("4 == 4")
        assert self.ev(t) is True

    def test_inequality(self):
        t = self.p("4 != 5")
        assert self.ev(t) is True
        t = self.p("'a' != 'a'")
        assert self.ev(t) is False

    def test_lt(self):
        t = self.p("4 < 5")
        assert self.ev(t) is True
        t = self.p("'ab' < 'ac' ")
        assert self.ev(t) is True
        assert self.evp("4 < 4") is False
        assert self.evp("5 < 4") is False

    def test_lte(self):
        assert self.evp("4 <= 5") is True
        assert self.evp("4 <= 4") is True
        assert self.evp("4 <= 3") is False

    def test_gt(self):
        assert self.evp("4 > 5") is False
        assert self.evp("4 > 4") is False
        assert self.evp("5 > 4") is True

    def test_gte(self):
        assert self.evp("4 >= 5") is False
        assert self.evp("4>=4") is True
        assert self.evp("5 >= 4") is True

    def test_and(self):
        assert self.evp("2 AND 5") == 5
        assert self.evp("'' AND 1") == ''
        assert self.evp("1 AND 0") == 0
        assert self.evp("1 AND 1") == 1
        assert self.evp("0 AND 1") == 0
        assert self.evp("0 AND 0") == 0
        assert self.evp("(1==0) AND (1/0)") is False

    def test_or(self):
        assert self.evp("2 OR 5") == 2
        assert self.evp("'' OR 5") == 5
        assert self.evp("1 OR (1/0) ") == 1
        assert self.evp("0 OR 0") == 0
        assert self.evp("0 OR 1") == 1
        assert self.evp("1 OR 0") == 1
        assert self.evp("1 OR 1") == 1

    def test_cond(self):
        assert self.evp("COND(2==5, 'a', 'b')") == 'b'
        assert self.evp("COND(TRUE, 'c', 1/0)") == 'c'
        assert self.evp("COND(FALSE, 1/0, 'c')") == 'c'
        assert self.evp("IF 1==1 THEN 5 ELSE 4") == 5
        assert self.evp("IF FALSE THEN '5' ELSE '4'") == '4'

    def test_modulo(self):
        assert self.evp("7 % 3") == 1
        assert self.evp("8 % 3") == 2

    def test_index(self):
        assert self.evp("'abcd'[1+1]") == 'c'

    def test_lambdas(self):
        assert self.evp("FUN[$a]($a+1)(2)") == 3
        assert self.evp("LAMBDA[$a]($a+1)(10,)") == 11
        f = self.evp("FUN[$a, $b = 1+2, *$c, $d, $e = 5, $f, **$kwargs]([$a, $b, $c, $d, $e, $f, $kwargs]) ")
        assert f(1, 2, 3, 4, d=4, f=12, g=8, h=10) == [1, 2, (3, 4), 4, 5, 12, {'g': 8, 'h': 10}]

        curry = self.evp("FUN[$fun, $first](FUN[$second]($fun($first,$second) ))")
        mult = self.evp("FUN[$first, $second]($first * $second)")
        mult2 = self.evp("FUN[$a,$b]($a * $b)")

        assert curry(mult, 4)(5) == 20
        assert curry(curry, mult2)(4)(5) == 20

        g = self.evp("FUN[$a, $c, $d](FUN[$a, $b = $a, $c=$c]([$a,$b,$c,$d])  )  ")
        f = g(1, 2, 3)
        assert f(4) == [4, 4, 2, 3]
        assert f(5) == [5, 5, 2, 3]
        assert f(0, 1) == [0, 1, 2, 3]
        assert f(0, 1, 10) == [0, 1, 10, 3]

    def test_list(self):
        assert self.evp("[1]") == [1]
        assert self.evp("[1+1] + [2+2,]") == [2, 4]

# TODO: Refactor to unittest at some point. Postponed, because semantics of lookups may change anyway.
def test_lookups(empty3cv: 'BaseCharVersion.BaseCharVersion'):
    # L1: BaseCharVersion.UserDataSet = empty3cv.lists[0]
    # L2: BaseCharVersion.UserDataSet = empty3cv.lists[1]
    # L3: BaseCharVersion.CoreRuleDataSet = empty3cv.lists[2]  # Core rule dataset
    l1set_from_string = lambda x, y: empty3cv.set_input(key=x, value=y, target_desc="D1")
    l2set_from_string = lambda x, y: empty3cv.set_input(key=x, value=y, target_desc="D2")
    l3set_from_string = lambda x, y: empty3cv.set_input(key=x, value=y, target_desc="D3")

    x = empty3cv.get('abc')
    assert isinstance(x, CharExceptions.DataError)
    l1set_from_string('a', 'T1')
    x = empty3cv.get('b.a')
    assert x == 'T1'
    x = empty3cv.get('__b__.a')
    assert isinstance(x, CharExceptions.DataError)
    l1set_from_string('b', '=$AUTO + 2')
    l2set_from_string('b', '10')
    l3set_from_string('b', '100')
    l2set_from_string('xxx', '=b + b + 1')
    x = empty3cv.get('yyy.xxx')
    assert x == 25
    l2set_from_string('indirect', '=GET("b")')
    assert empty3cv.get('indirect') == 12
    l1set_from_string('x.c', '=$AUTO')
    l2set_from_string('x.c', '=$AUTO')
    l2set_from_string('c', '=[$QUERY,$NAME]')
    assert empty3cv.get('c') == ['c', 'c']
    assert empty3cv.get('y.c') == ['y.c', 'c']
    l1set_from_string('c', '=$AUTO')
    assert empty3cv.get('y.c') == ['c', 'c']
    l1set_from_string('c', '=$AUTOQUERY')
    assert empty3cv.get('y.c') == ['y.c', 'c']
    assert empty3cv.get('x.c') == ['x.c', 'c']
    assert empty3cv.get('x.y.c') == ['x.c', 'c']
    l1set_from_string('anotherindirect', '=GET("x." + "y.c")')
    assert empty3cv.get('anotherindirect') == ['x.c', 'c']
    l3set_from_string('__fun__.f', "=FUN[$a]($a * $a)")
    l3set_from_string('__fun__.g', '=__fun__.f')
    l3set_from_string('fun.f', "10")
    l2set_from_string('fun.h', '=FUN[$b]($b + 100)')
    l1set_from_string('fff', '=H(3)')
    assert empty3cv.get('fff') == 103
    l1set_from_string('fff', '=H($b=4)')
    assert empty3cv.get('fff') == 104
    l1set_from_string('fff', '=H($c=4)')
    assert isinstance(empty3cv.get('fff'), CharExceptions.DataError)
    l1set_from_string('fff', '=H("b"=5)')
    assert empty3cv.get('fff') == 105
    # noinspection PyUnusedLocal
    x = empty3cv.get('__fun__.f')
    l1set_from_string('fff', '=F(3)')
    assert empty3cv.get('fff') == 9
    l1set_from_string('fff', '=G(3)')
    assert empty3cv.get('fff') == 9
    l1set_from_string('lookup', '=FUN[$a](GET($a))')
    lookup = empty3cv.get('lookup')
    assert lookup('fff') == 9
    assert lookup('x.y.c') == ['x.c', 'c']

    l3set_from_string('ref', '1')
    l2set_from_string('ref', '=$AUTO + $AUTO')
    l1set_from_string('ref', '=$AUTO + $AUTO + 10')
    assert empty3cv.get('ref') == 14
