from . import Parser

p = Parser.parser.parse
ev = lambda T : T.eval_ast(None, {})
evp = lambda string : ev(p(string))

def test_add():
    T = p("1 + 5")
    assert ev(T) == 6

def test_sub():
    assert evp("2 - 6") == -4

def test_true():
    assert evp("TRUE") == True

def test_false():
    assert evp("FALSE") == False

def test_string_lit():
    T = p("'a1b' + 'X' + 'Y' * 3 + 'Z'")
    assert ev(T) == 'a1bXYYYZ'

def test_float():
    T = p("1.5 + 2.5")
    assert ev(T) == 4.0

def test_proddiv():
    T = p("4*5+9/2")
    assert ev(T) == 24.5

def test_idiv():
    T = p("9//2")
    assert ev(T) == 4

def test_bracket():
    T = p(" ((4+5)*3) ")
    assert ev(T) == 27

def test_variable():
    T = p("$var + 4")
    assert T.eval_ast(None, {'var': 7}) == 11

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
    assert f(1,2,3,4, d=4, f=12, g = 8, h = 10) == [1,2,(3,4),4, 5,12,{'g':8, 'h':10} ]

    curry = evp("FUN[$fun, $first](FUN[$second]($fun($first,$second) ))")
    mult = evp("FUN[$first, $second]($first * $second)")
    mult2 = evp("FUN[$a,$b]($a * $b)")

    assert curry(mult, 4)(5) == 20
    assert curry(curry, mult2)(4)(5) == 20
