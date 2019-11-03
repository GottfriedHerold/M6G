from . import Parser
from . import CharVersion
from . import CharExceptions

p = Parser.parser.parse
ev = lambda T: T.eval_ast(None, {})
evp = lambda s: ev(p(s))

def test_add():
    T = p("1 + 5")
    assert ev(T) == 6

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

def test_variable():
    old = Parser._ALLOWED_SPECIAL_ARGS
    try:
        Parser._ALLOWED_SPECIAL_ARGS |= {'var'}
        T = p("$var + 4")
        assert T.eval_ast(None, {'var': 7}) == 11
    finally:
        Parser._ALLOWED_SPECIAL_ARGS = old

    try:
        T = p("$var + 4")
    except Parser.CGParseException:
        pass
    else:
        assert False

def test_equality():
    T = p("4 == 5")
    assert ev(T) == False
    T = p("4 == 4")
    assert ev(T) == True

def test_inquality():
    T = p("4 != 5")
    assert ev(T) == True
    T = p("'a' != 'a'")
    assert ev(T) == False

def test_lt():
    T = p("4 < 5")
    assert ev(T) == True
    T = p("'ab' < 'ac' ")
    assert ev(T) == True
    assert evp("4 < 4") == False
    assert evp("5 < 4") == False

def test_lte():
    assert evp("4 <= 5") == True
    assert evp("4 <= 4") == True
    assert evp("4 <= 3") == False

def test_gt():
    assert evp("4 > 5") == False
    assert evp("4 > 4") == False
    assert evp("5 > 4") == True

def test_gte():
    assert evp("4 >= 5") == False
    assert evp("4>=4") == True
    assert evp("5 >= 4") == True

def test_and():
    assert evp("2 AND 5") == 5
    assert evp("'' AND 1") == ''
    assert evp("1 AND 0") == False
    assert evp("1 AND 1") == True
    assert evp("0 AND 1") == False
    assert evp("0 AND 0") == False
    assert evp("(1==0) AND (1/0)") == False

def test_or():
    assert evp("2 OR 5") == 2
    assert evp("'' OR 5") == 5
    assert evp("1 OR (1/0) ") == True
    assert evp("0 OR 0") == False
    assert evp("0 OR 1") == True
    assert evp("1 OR 0") == True
    assert evp("1 OR 1") == True

def test_cond():
    assert evp("COND(2==5, 'a', 'b')") == 'b'
    assert evp("COND(TRUE, 'c', 1/0)") == 'c'
    assert evp("COND(FALSE, 1/0, 'c')") == 'c'

def test_modulo():
    assert evp("7 % 3") == 1
    assert evp("8 % 3") == 2

def test_index():
    assert evp("'abcd'[1+1]") == 'c'

def test_lambdas():
    assert evp("FUN[$a]($a+1)(2)") == 3
    assert evp("LAMBDA[$a]($a+1)(10)") == 11
    f = evp("FUN[$a, $b = 1+2, *$c, $d, $e = 5, $f, **$kwargs](LIST($a, $b, $c, $d, $e, $f, $kwargs)) ")
    assert f(1, 2, 3, 4, d=4, f=12, g=8, h=10) == [1, 2, (3, 4), 4, 5, 12, {'g': 8, 'h': 10}]

    curry = evp("FUN[$fun, $first](FUN[$second]($fun($first,$second) ))")
    mult = evp("FUN[$first, $second]($first * $second)")
    mult2 = evp("FUN[$a,$b]($a * $b)")

    assert curry(mult, 4)(5) == 20
    assert curry(curry, mult2)(4)(5) == 20

    g = evp("FUN[$a, $c, $d](FUN[$a, $b = $a, $c=$c](LIST($a,$b,$c,$d))  )  ")
    f = g(1, 2, 3)
    assert f(4) == [4, 4, 2, 3]
    assert f(5) == [5, 5, 2, 3]
    assert f(0, 1) == [0, 1, 2, 3]
    assert f(0, 1, 10) == [0, 1, 10, 3]

def test_lookups(empty3cv: 'CharVersion.CharVersion'):
    L1:CharVersion.UserDataSet = empty3cv.lists[0]
    L2:CharVersion.UserDataSet = empty3cv.lists[1]
    L3:CharVersion.CoreRuleDataSet = empty3cv.lists[2]  # Core rule dataset

    x = empty3cv.get('abc')
    assert isinstance(x, CharExceptions.DataError)
    L1.set_from_string('a', 'T1')
    x = empty3cv.get('b.a')
    assert x == 'T1'
    x = empty3cv.get('__b__.a')
    assert isinstance(x, CharExceptions.DataError)
    L1.set_from_string('b', '=$AUTO + 2')
    L2.set_from_string('b', '10')
    L3.set_from_string('b', '100')
    L2.set_from_string('xxx', '=b + b + 1')
    x = empty3cv.get('yyy.xxx')
    assert x == 25
    L1.set_from_string('x.c', '=$AUTO')
    L2.set_from_string('x.c', '=$AUTO')
    L2.set_from_string('c', '=LIST($QUERY,$NAME)')
    assert empty3cv.get('c') == ['c', 'c']
    assert empty3cv.get('y.c') == ['y.c', 'c']
    L1.set_from_string('c', '=$AUTO')
    assert empty3cv.get('y.c') == ['c', 'c']
    L1.set_from_string('c', '=$AUTOQUERY')
    assert empty3cv.get('y.c') == ['y.c', 'c']
    assert empty3cv.get('x.c') == ['x.c', 'c']
    assert empty3cv.get('x.y.c') == ['x.c', 'c']
    L3.set_from_string('__fun__.f', "=FUN[$a]($a * $a)")
    L3.set_from_string('__fun__.g', '=__fun__.f')
    L3.set_from_string('fun.f', "10")
    L2.set_from_string('fun.h', '=FUN[$b]($b + 100)')
    L1.set_from_string('fff', '=H(3)')
    assert empty3cv.get('fff') == 103
    x = empty3cv.get('__fun__.f')
    L1.set_from_string('fff', '=F(3)')
    assert empty3cv.get('fff') == 9
    L1.set_from_string('fff', '=G(3)')
    assert empty3cv.get('fff') == 9



