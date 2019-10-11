from .Regexps import re_key_regular, re_key_any, re_key_restrict

def test_re_key_regular():
    re_key = re_key_regular
    assert re_key.fullmatch("a_b_c")
    assert re_key.fullmatch("") is None
    assert not re_key.fullmatch(".a")
    assert not re_key.fullmatch(".")
    assert not re_key.fullmatch("a.")
    assert re_key.fullmatch("_a_._b_._c_d_")
    assert not re_key.fullmatch("__a.b")
    assert not re_key.fullmatch("a__.b")
    assert not re_key.fullmatch("a.__b")
    assert not re_key.fullmatch("a.b__")
    assert re_key.fullmatch("a__b._c__d_")
    assert not re_key.fullmatch("_a_.._b_")
    assert re_key.fullmatch("AaZz_.AaZzCc_")
    assert not re_key.fullmatch("a;b")

def test_re_key_any():
    re_key = re_key_any
    assert re_key.fullmatch("a_b_c")
    assert re_key.fullmatch("") is None
    assert not re_key.fullmatch(".a")
    assert not re_key.fullmatch(".")
    assert not re_key.fullmatch("a.")
    assert re_key.fullmatch("_a_._b_._c_d_")
    assert re_key.fullmatch("__a.b")
    assert re_key.fullmatch("a__.b")
    assert re_key.fullmatch("a.__b")
    assert re_key.fullmatch("a.b__")
    assert re_key.fullmatch("a__b._c__d_")
    assert not re_key.fullmatch("_a_.._b_")
    assert re_key.fullmatch("AaZz_.AaZzCc_")
    assert not re_key.fullmatch("a;b")

def test_re_key_restrict():
    re_key = re_key_restrict
    assert not re_key.fullmatch("a_b_c")
    assert re_key.fullmatch("") is None
    assert not re_key.fullmatch(".a")
    assert not re_key.fullmatch(".")
    assert not re_key.fullmatch("a.")
    assert not re_key.fullmatch("_a_._b_._c_d_")
    assert re_key.fullmatch("__a.b")
    assert re_key.fullmatch("a__.b")
    assert re_key.fullmatch("a.__b")
    assert re_key.fullmatch("a.b__")
    assert not re_key.fullmatch("a__b._c__d_")
    assert not re_key.fullmatch("_a_.._b_")
    assert not re_key.fullmatch("AaZz_.AaZzCc_")
    assert not re_key.fullmatch("a;b")
    assert re_key.fullmatch("__a__")
    assert re_key.fullmatch("__a__.__b__.__c__")
    assert re_key.fullmatch("a.__b__.c.__d__.e")
    assert re_key.fullmatch("a__.b.c.__def__g")
    match = re_key.fullmatch("__a__.b.__c.d")
    assert match.group('head') == "__a__.b.__c"
    assert match.group('restrict') == "__c"
    assert match.group('tail') == ".d"
    match = re_key.fullmatch("___a___")
    assert match.group('head') == match.group('restrict') == "___a___"
    assert match.group('tail') == ""