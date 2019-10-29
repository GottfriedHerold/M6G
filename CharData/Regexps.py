"""
    Recurring regular expressions
"""

import re

#re_key_any.fullmatch("abc.def") matches for valid keys used as paths in our databases
#re_key_regular matches for valid keys, whose consituent parts do not begin or end with double underscores
#re_key_restrict matches for keys, where one of the constituent begins or ends with an underscore
#for the latter, the resulting match object M = re_key_restrict.fullmatch("__a__.__b__.c")
#has the LAST such constituent availible as M.group('restrict') == "__b__"
#M.group('tail') == ".c" is what follows the last such constituent (note that this is empty or begins with ".")
#M.group('head') is everything up to tail (exclusive).
# See test_regexps.py for examples
re_key_regular = re.compile(r"(?:(?!__)[a-z_]+(?<!__))(?:\.(?!__)[a-z_]+(?<!__))*")
re_key_any = re.compile(r"[a-z_]+(?:\.[a-z_]+)*")
re_key_restrict = re.compile(r"(?P<head>(?:[a-z_]+\.)*(?P<restrict>(?:__[a-z_]+)|(?:[a-z_]+__)))(?P<tail>(?:\.(?!__)[a-z_]+(?<!__))*)")

# 
re_number_int = re.compile(r"[0-9]+")
re_number_float = re.compile(r"[0-9]+[.][0-9]+")

re_argname = re.compile(r"[$][a-z_]+")
re_special_arg = re.compile(r"[$][A-Z][a-zA-Z_]*")
re_funcname = re.compile(r"[A-Z]+")