"""
    Recurring regular expressions in the CharGen Expression Language
"""
from __future__ import annotations
from typing import Final
import re

# re_key_any.fullmatch("abc.def") matches for valid keys used as paths in our databases
# re_key_regular matches for valid keys, whose constituent parts do not begin or end with double underscores
# re_key_restrict matches for keys, where one of the constituent begins or ends with an underscore
# for the latter, the resulting match object M = re_key_restrict.fullmatch("__a__.__b__.c")
# has the LAST such constituent available as M.group('restrict') == "__b__"
# M.group('tail') == ".c" is what follows the last such constituent (note that this is empty or begins with ".")
# M.group('head') is everything up to tail (exclusive).
# See test_regexps.py for examples
re_key_regular: Final = re.compile(r"(?:(?!__)[a-z_]+(?<!__))(?:\.(?!__)[a-z_]+(?<!__))*")
re_key_any: Final = re.compile(r"[a-z_]+(?:\.[a-z_]+)*")
re_key_restrict: Final = re.compile(r"(?P<head>(?:[a-z_]+\.)*(?P<restrict>(?:__[a-z_]+)|(?:[a-z_]+__)))(?P<tail>(?:\.(?!__)[a-z_]+(?<!__))*)")

# regular expression for tokenizing CharGen Expression Language
re_number_int: Final = re.compile(r"[0-9]+")
re_number_float: Final = re.compile(r"[0-9]+[.][0-9]+")

re_argname: Final = re.compile(r"[$][a-z_]+")
re_special_arg: Final = re.compile(r"[$][A-Z][a-zA-Z_]*")
re_funcname: Final = re.compile(r"[A-Z]+")
re_funcname_lowercased: Final = re.compile(r"[a-z]+")

def valid_key(key: str) -> bool:
    match = re_key_any.fullmatch(key)
    assert match
    split_key = key.split(".")


    return True
