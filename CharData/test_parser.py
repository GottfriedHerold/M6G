from . import Parser
from . import CharVersion
from . import CharExceptions

p = Parser.parser.parse
ev = lambda t: t.eval_ast(None, {})
evp = lambda s: ev(p(s))


def test_rules():
    for sa in Parser.special_args.values():
        assert sa[0] in Parser.tokens
    assert Parser.CONTINUE_LOOKUP not in Parser.special_args
    for keyword in Parser.keywords:
        assert keyword == keyword.upper()


def test_add():
    t = p("1 + 5")
    assert ev(t) == 6


def test_sub():
    assert evp("2 - 6") == -4


def test_true():
    assert evp("TRUE")


def test_false():
    assert not evp("FALSE")


def test_string_lit():
    t = p("'a1b' + 'X' + 'Y' * 3 + 'Z'")
    assert ev(t) == 'a1bXYYYZ'


def test_float():
    t = p("1.5 + 2.5")
    assert ev(t) == 4.0


def test_proddiv():
    t = p("4*5+9/2")
    assert ev(t) == 24.5


def test_idiv():
    t = p("9//2")
    assert ev(t) == 4


def test_bracket():
    t = p(" ((4+5)*3) ")
    assert ev(t) == 27


# noinspection PyProtectedMember
def test_variable():
    old = Parser._ALLOWED_SPECIAL_ARGS
    try:
        Parser._ALLOWED_SPECIAL_ARGS |= {'test_var'}
        t = p("$test_var + 4")
        assert t.eval_ast(None, {'test_var': 7}) == 11
    finally:
        Parser._ALLOWED_SPECIAL_ARGS = old

    try:
        # noinspection PyUnusedLocal
        t = p("$test_var + 4")
    except Parser.CGParseException:
        pass
    else:
        assert False


def test_equality():
    t = p("4 == 5")
    assert ev(t) is False
    t = p("4 == 4")
    assert ev(t) is True


def test_inequality():
    t = p("4 != 5")
    assert ev(t) is True
    t = p("'a' != 'a'")
    assert ev(t) is False


def test_lt():
    t = p("4 < 5")
    assert ev(t) is True
    t = p("'ab' < 'ac' ")
    assert ev(t) is True
    assert evp("4 < 4") is False
    assert evp("5 < 4") is False


def test_lte():
    assert evp("4 <= 5") is True
    assert evp("4 <= 4") is True
    assert evp("4 <= 3") is False


def test_gt():
    assert evp("4 > 5") is False
    assert evp("4 > 4") is False
    assert evp("5 > 4") is True


def test_gte():
    assert evp("4 >= 5") is False
    assert evp("4>=4") is True
    assert evp("5 >= 4") is True


def test_and():
    assert evp("2 AND 5") == 5
    assert evp("'' AND 1") == ''
    assert evp("1 AND 0") == 0
    assert evp("1 AND 1") == 1
    assert evp("0 AND 1") == 0
    assert evp("0 AND 0") == 0
    assert evp("(1==0) AND (1/0)") is False


def test_or():
    assert evp("2 OR 5") == 2
    assert evp("'' OR 5") == 5
    assert evp("1 OR (1/0) ") == 1
    assert evp("0 OR 0") == 0
    assert evp("0 OR 1") == 1
    assert evp("1 OR 0") == 1
    assert evp("1 OR 1") == 1


def test_cond():
    assert evp("COND(2==5, 'a', 'b')") == 'b'
    assert evp("COND(TRUE, 'c', 1/0)") == 'c'
    assert evp("COND(FALSE, 1/0, 'c')") == 'c'
    assert evp("IF 1==1 THEN 5 ELSE 4") == 5
    assert evp("IF FALSE THEN '5' ELSE '4'") == '4'


def test_modulo():
    assert evp("7 % 3") == 1
    assert evp("8 % 3") == 2


def test_index():
    assert evp("'abcd'[1+1]") == 'c'


def test_lambdas():
    assert evp("FUN[$a]($a+1)(2)") == 3
    assert evp("LAMBDA[$a]($a+1)(10,)") == 11
    f = evp("FUN[$a, $b = 1+2, *$c, $d, $e = 5, $f, **$kwargs]([$a, $b, $c, $d, $e, $f, $kwargs]) ")
    assert f(1, 2, 3, 4, d=4, f=12, g=8, h=10) == [1, 2, (3, 4), 4, 5, 12, {'g': 8, 'h': 10}]

    curry = evp("FUN[$fun, $first](FUN[$second]($fun($first,$second) ))")
    mult = evp("FUN[$first, $second]($first * $second)")
    mult2 = evp("FUN[$a,$b]($a * $b)")

    assert curry(mult, 4)(5) == 20
    assert curry(curry, mult2)(4)(5) == 20

    g = evp("FUN[$a, $c, $d](FUN[$a, $b = $a, $c=$c]([$a,$b,$c,$d])  )  ")
    f = g(1, 2, 3)
    assert f(4) == [4, 4, 2, 3]
    assert f(5) == [5, 5, 2, 3]
    assert f(0, 1) == [0, 1, 2, 3]
    assert f(0, 1, 10) == [0, 1, 10, 3]

def test_list():
    assert evp("[1]") == [1]
    assert evp("[1+1] + [2+2,]") == [2, 4]

def test_lookups(empty3cv: 'CharVersion.CharVersion'):
    # L1: CharVersion.UserDataSet = empty3cv.lists[0]
    # L2: CharVersion.UserDataSet = empty3cv.lists[1]
    # L3: CharVersion.CoreRuleDataSet = empty3cv.lists[2]  # Core rule dataset
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
