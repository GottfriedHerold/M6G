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
re_key_regular = re.compile(r"(?:(?!__)[a-zA-Z_]+(?<!__))(?:\.(?!__)[a-zA-Z_]+(?<!__))*")
re_key_any = re.compile(r"[a-zA-Z_]+(?:\.[a-zA-Z_]+)*")
re_key_restrict = re.compile(r"(?P<head>(?:[a-zA-Z_]+\.)*(?P<restrict>(?:__[a-zA-Z_]+)|(?:[a-zA-Z_]+__)))(?P<tail>(?:\.(?!__)[a-zA-Z_]+(?<!__))*)")