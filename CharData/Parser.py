"""
    This is the parser that converts input strings such as into abstract syntax trees (ASTs) with an evaluation routine
    e.g. T = parser.parse("11+5") yields an abstract syntax tree T with
    T.eval_ast(None,{})  == 16. (The arguments to T.eval_ast are irrelevant for this particular example)

    We use PLY (Python lex/yacc) to build the parser.
    Note that PLY makes extensive use of introspection, i.e. PLY analyzes the function definitions in this Parser.py
    file and looks for functions whose names match certain patterns and extracts lexer/parser rules from its docstrings.

    In particular, function names and docstrings carry actual semantics in this file!

    The usual workflow is that an input string such as "11 + 5" is first tokenized by ply.lex into a list of tokens
    [("INT",11), ("+","+"), ("INT", 5)].
    Next (the actual implementation of PLY interleaves tokenizing and parsing in some way),
    ply.yacc generates an abstract syntax tree from this list of tokens.
    In the given example, the tree would have a root node for "Addition operation" with 2 child leaves
    encoding "integer literal 11" and "integer literal 5".
    Each such node has an eval_ast function, where the children evaluate to 11 and 5. the root evaluates to 16.
"""

# TODO: Some key features are still missing here, notably:
# - $DIR() like functionalities that allow querying what key are present in the database.
#   This is not really a feature of the browser but rather of data sources, as such information should
#   be exposed via (read-only, for the user) __dir__ - like-entries in the database.
# - optional arguments to GET that allows GET("a.b", with={a.c="xyy"}) queries to get the key a.b and evaluate it as-if
#   the entry under a.c was "xyz". Might require turning GET into a core-constant to have variable argument number
# - .x syntax as shorthand
# - convenience functions to work with strings like "a.b.c" (converting to/from list of strings etc.)
# - convenience functions to work with lists (map-reduce etc.), implement loops more easily etc.
# - make error handling more usable (requires web-interface to test how it "feels like")

# Concrete convenience functions will probably be added as one writes database-entries for a given set of RPG rules to
# actually match demand.

from typing import TYPE_CHECKING, Union

import ply.lex as lex
import ply.yacc as yacc
# ply.lex.TOKEN is a decorator to associate regexps with tokenizer rules.
# The "normal" way is to set a docstring to the regexp, which (apart from all the qualms I have about giving
# docstrings semantics) does not work if the regexp is an import such as re_key_any.
from ply.lex import TOKEN
from .Regexps import re_key_any, re_number_float, re_number_int, re_argname, re_funcname, re_special_arg
from .CharExceptions import DataError, CGParseException, CGEvalException

# We need CharVersion for type annotations. Unfortunately, this would create circular imports, which are OK only
# while statically type-checking, but not otherwise.
if TYPE_CHECKING:
    from . import CharVersion

# Recognized keywords by the tokenizer.
# ply.lex generates tokens with a value and a type. For keywords in this list, value == type == keyword string.
# keywords must be allcaps.

keywords = [
    'COND',  # may turn into core_constant
    'OR',
    'AND',
    'NOT',
    'FUN',  # alternative: LAMBDA is also recognized. This is handled in the tokenizer code, not in this list to
            # to avoid having two separate token values.
    # 'LAMBDA', # For this, we want type = 'FUN', value = 'LAMBDA'
    'GET',  # may need turn into core constant
    'IF',
    'THEN',
    'ELSE',
]

_EMPTYSET = frozenset()

# Python constants (dict is a constant of type callable) that are exposed as additional keywords.

core_constants = {
    'LIST': list,
    'DICT': dict,  # not sure whether this works on all interpreters
    'EMPTYSET': _EMPTYSET,
    'True': True,
    'False': False,
    'TRUE': True,
    'FALSE': False,
}

# tokens of the form $Name (with a literal $), where Name starts with a capital letter will be recognized by the lexer
# iff(!) Name.upper() is in the special_args dict. Note that $foo (for lowercase foo) is recognized as a variable with
# name foo (used in lambdas); special_args should be used for similar purposes, in particular for things that behave
# like environmental variables that need to be set externally by the caller when actually evaluating. Or more generally,
# things that are in some sense context-dependent.

special_args = {
    # keys are what is recognized as $Key (after uppercasing, so keys need to be capitalized here).
    # values are pairs (TOKEN, Value) to mean that this gets tokenized as a token of type TOKEN with value Value.
    # TOKEN needs to be in the tokens list. Value may later be used by the parser rules after tokenizing.
    # In particular, for TOKEN == 'ARGNAME' or 'SPECIALARG',
    # Value determines which variable is looked up from the context dict
    # in eval_ast, i.e. under which name the binding is supplied by the external caller.
    # The distinction between SPECIALARG and ARGNAME tokens is only that SPECIALARG tokens can not be used to
    # introduce new variable names in lambda definition's variable lists.
    # Values for these special arguments should begin with a capital letter in order to be from a set of names disjoint
    # from internal user-provided variables used in lambdas. They also need to be in _ALLOWED_SPECIAL_ARGS below in
    # order to escape as free variables.
    # For TOKEN == 'AUTO', context[Value] is what gets passed as new query string.

    'A': ('AUTO', 'Name'),  # $AUTO evaluates to whatever it would if there was no entry and lookup continued, but
    # with query string $NAME (i.e. if the current entry was queried directly)
    'AUTO': ('AUTO', 'Name'),
    'AQ': ('AUTO', 'Query'),  # $AUTOQUERY or $AQ evaluates to whatever it would if there was no entry and lookup
    # continued (with query string $QUERY)
    'AUTOQUERY': ('AUTO', 'Query'),
    'Q': ('SPECIALARG', 'Query'),  # $QUERY is the query string, usually equals to $NAME.
    # It may differ due to lookup rules.
    'QUERY': ('SPECIALARG', 'Query'),
    'NAME': ('SPECIALARG', 'Name'),  # $Name is set by the caller. It is supposed to be set to the database key which
    # holds the entry.
}

# CONTINUE_LOOKUP is a special environmental variable that is used internally in the lookup procedure.
# (i.e. there is a special variable $Continue that is reserved for internal usage.)
# It can not be used as a variable in lambdas (enforced by Continue being uppercase).
CONTINUE_LOOKUP = 'Continue'

# Parse results are abstract syntax trees, which may contain lambdas and (bound or free) variables $foo.
# Every tree node knows which variables are free in its subtree.
# In a valid parse, only Elements from _ALLOWED_SPECIAL_ARGS are allowed to "escape" as free variables at the root node.
# Such escaping variables must then be set by the caller when evaluating the parse result.
_ALLOWED_SPECIAL_ARGS = frozenset({'Name', 'Query', CONTINUE_LOOKUP})

# PLY looks for a variable named tokens (and literals) to determine the set of tokens in its parsing rules later.
tokens = [
             'STRING',  # Quote - enclosed string
             'IDIV',  # // (integral division, as opposed to /, which gives floats)
             'INT',  # Integer
             'FLOAT',  # Floats
             'FUNCNAME',  # FUNCTION (all - caps)
             'LOOKUP',  # attr.strength
             'EQUALS',  # == (equality comparison)
             'NEQUALS',  # != (inequality comparison)
             'LTE',  # <=
             'GTE',  # >=
             'ARGNAME',  # $argument
             'SPECIALARG',  # $Argument
             'AUTO',  # $A[uto] - gets default value (i.e. continues lookup).
             'CORECONSTANT',  # hard-coded constants (which may be of type function)
         ] + keywords


# PLY.lex generates tokenizer rules from definitions with names t_foo(token) and the special variable named literals.
# token.type determines the type of token we have (defaults to "foo" in t_foo definitions unless foo is a special name),
# which is what our parser rules below refer to.
# token.value is the actual payload of the token. (e.g. the actual number in a token of type "number"). Defaults to
# the actual substring of the input that generated the regexp match.
# Tokenizer matches are determined by regular expressions given by the docstring or @TOKEN decorator.
# token.type must be either a literal or from the tokens list above. t_foo(token) function defs must return the
# (possibly modified) token or None or raise an exception. If None is returned, the input substring is consumed without
# generating a token for the parser.

# Note: Order matters!
# Function defs take priority (in order of definition),
# then t_TOKEN = regexp defs (in order of decreasing length of regexp)
# then literals


# noinspection PySingleQuotedDocstring
def t_STRING(token):  # strings delimited by either ' or " (left and right delimeters must match)
    r"(?:'[^']*')|" r'(?:"[^"]*")'  # Allow either ' or " as delimeters (Python-like)
    token.value = token.value[1:-1]  # strip the quotation marks already at the lexer stage
    return token


@TOKEN(re_number_float.pattern)  # floating numbers with a .
def t_FLOAT(token):
    token.value = float(token.value)
    return token


# This must come after t_FLOAT (so that e.g. the prefix "5" of 5.4 is not tokenized as an int)
@TOKEN(re_number_int.pattern)  # integers
def t_INT(token):
    token.value = int(token.value)
    return token


# This is a single rule for
# -Keywords OR AND NOT etc
# -Functions FUNC
# Special References $Name etc.
# local variables $name
# references to other data fields attr.strength
# These are pooled as a single t_WORD rule in order to ensure that strings such as Ab do not parse as separate tokens
# A and b. This way we get an error "Did not recognize string Ab" instead of a mis-parse or a confusing error.
# Note that no tokens of actual type "WORD" exist: we always overwrite token.type
# noinspection PySingleQuotedDocstring
def t_WORD(token):
    r"[$]?[a-z._A-Z]+"  # We match any combination of letters, dots and underscores that optionally starts with $
    if token.value in core_constants:
        token.type = 'CORECONSTANT'
    elif re_special_arg.fullmatch(token.value):  # r"[$][A-Z][a-zA-Z_]*" : Tokens of the Form $Foo or $FOO
        # We only accept if FOO is from the special_args dict above, which contains (type,value) as special_args['FOO']
        try:
            spec = special_args[token.value[1:].upper()]  # [1:] strips the leading $
        except KeyError:
            raise SyntaxError("Invalid argument name " + token.value)
        else:
            token.type = spec[0]
            token.value = spec[1]
    elif re_argname.fullmatch(token.value):  # r"[$][a-z_]+" : Tokens of the form $foo: internal variable names
        token.type = 'ARGNAME'
        token.value = token.value[1:]  # strip leading $
    elif re_funcname.fullmatch(token.value):  # "[A-Z]+": Function names and keywords are ALLCAPS. Allow _'s ?
        token.type = 'FUNCNAME'
        if token.value in keywords:
            token.type = token.value
        if token.value == 'LAMBDA':  # special-cased, because we don't need separate token.type = 'LAMBDA' type.
            token.type = 'FUN'
    elif re_key_any.fullmatch(token.value):  # complicated regexp, matching lookups attr.strength etc.
        token.type = 'LOOKUP'
    else:
        raise SyntaxError("Did not recognize String " + token.value)
    return token


# This is called by PLY.lex in case of tokenizer errors, i.e. when no rule matches a prefix of the remaining input.
def t_error(token):
    # for now, sets the remaining input string as empty: we are done parsing.
    # Otherwise, we risk an endless loop if the exception is handled and parsing continues.
    token.lexer.input("")
    raise SyntaxError("Could not parse formula")


# t_ignore is a list of characters that are simply ignored by the parser (unless part of a match before,
# e.g. whitespace in string literals), but may act as separators.
t_ignore = ' \t\n\r\f\v'  # ignore (ASCII) whitespace. We complain about Non-Ascii unicode whitespace.

# t_foo = string specifications and literals take precedence in order of length. So // will match IDIV and not / twice.
t_IDIV = r"//"
t_EQUALS = r"=="
t_NEQUALS = r"!="
t_LTE = r"<="
t_GTE = r">="

# literals will generate single literal tokens
literals = "+-*/%()[],<>={}:"
# Note: While we have [] for indexing into iterables, membership access via "." is missing intentionally!
# In fact, allowing this might give remote code execution. The issue is that python objects carry references to
# their definition context via __globals__, __module__ etc. and these would become accessible.
# If the signing key for the session cookies leaks, an attacker can create forged session cookies.
# Since cookies may contain (supposedly signed) pickled python objects, an attacker can hijack pickle for remote code
# execution.

# use PLY.lex to actually generate the lexer now.
lexer = lex.lex()


# We parse the input string into an abstract syntax tree object of type (derived from) AST.
# (non-leaf nodes correspond to operations, children to operands, leafs to literals)
# This is an instance of a class (derived from) AST, whose
# actual derived class determines the type of object.
# (e.g. AST_Sum for an addition, AST_Mult for a multiplication)
# t's children are stored in t.child[0], ...
# The classvariable typedesc is a string denoting the type of operation.
# It is only used for printing (which in turn is only for debugging)
# ASTs are the result from parsing the input string.
# NOTE: The result of parsing must be purely a function of the input string. There is no dependency on
# other data sources for the references etc. These dependencies only come into play when actually evaluating.
# Furthermore, the structure of ASTs ist such that it should be easy to serialize them.

# To actually evaluate the AST instance T, call T.eval_ast(data_list, context)
# data_list is the list of data sources, used to evaluate (database) references.
# context is a dict for variables $arg = value that may appear.
# External callers should usually only set $Name and $Query.
# (context is mostly used internally to implement lambdas INSIDE ASTs. Externally set args are capitalized)

# For function definitions and function call expressions, we have the following non-obvious choices:

# For a function call f(a,b,c), we have an AST_FunctionCall node with children f,a,b,c (in that order), where
# f,a,b,c are ASTs themselves of appropriate types.
# For a function call f(a, *b,**c, $name  = d), we have an AST_FunctionCall node with children f,a,b,c,d.
# The subclass of AST of a,b,c do not tell that this a *,** or namebind-expression:
# This information is *not* part of the AST's tree structure. (there is no AST subclass for "star-expression" etc.)
# Rather, a,b,c,d have an object variable a.argtype denoting "starred-ness" and optionally d.argname = "name".

# For a function definition FUN[$a,$b,*$c]($a+$b), we have an AST_LAMBDA. AST_Lambdas always have exactly 2 children:
# The right child is an AST for the function body ($a+$b in this example). The left child is *not* an AST, but
# rather a (possibly empty) list of tuples, where each tuple entry encodes the variable name, its type (*-ed-ness and
# whether there is a default argument) and optionally default argument (which is an AST).


class AST:
    """
    Abstract syntax tree class. Actual objects are from derived classes.

    Use eval_ast(data_list, context) to evaluate the AST.
    needs_env contains the set of (possibly implicit) free variables in the subtree.
    """
    typedesc = 'AST'  # for debug printing. Should never be used on parent class.
    needs_env = _EMPTYSET  # default if need_env is never set for a particular object.

    def __init__(self, *kw, needs_env=None):
        """ Default constructor for AST nodes. Collect and stores the arguments as child nodes
            and sets the set of free variables in a default way (either union of children or provided by caller)
            If more complicated behaviour is needed, the derived class needs to handle that.
            :param kw:  Arbitary positional arguments are stored in self.child (which is a list)
                        These are usually ASTs (the exception being argument lists of lambda defs and calls).
            :param needs_env: set of appearing free variables.
                            Defaults to the union of the child nodes (we assume these are ASTs)
            Note that some derived classes may override __init__ without calling super.
        """
        # TODO: Check if last statement in docstring is still true.
        self.child = kw
        if needs_env is None:
            self.needs_env = _EMPTYSET.union(*[x.needs_env for x in kw])
        else:
            self.needs_env = needs_env

    def __str__(self):  # Debug only, may be overridden in leaf nodes. Note that self.typedesc is always overridden.
        return self.typedesc + '[' + ", ".join([str(x) for x in self.child]) + ']'

    def eval_ast(self, data_list: 'CharVersion.CharVersion', context: dict):
        """
        evaluates the ast within the given context.
        IMPORTANT: eval_ast can return lambdas which may capture data_list and context possibly *by reference*.
        For data_list, we only ever hand it through, but for context, do not rely on stable behaviour and never modify
        a dict after it is passed to eval_ast for the lifetime of the result as an external caller.

        :param data_list: List of data sources used for lookups. Of type CharVersion or None.
        :param context: Dict of variables used in evaluations. External callers need to supply those in self.needs_env.
        :return: result of evaluation.
        """
        raise NotImplementedError()  # pure virtual method


class AST_BinOp(AST):
    """
    pure virtual class used for AST nodes of binary operations. eval_fun is used for the actual binary operation.
    This class merely does error propagation (Error op anything == anything op Error == Error)
    common to all binary operations op.
    """
    typedesc = 'Binary Op'  # should never be used.

    def eval_ast(self, data_list, context: dict):
        left = self.child[0].eval_ast(data_list, context)
        if isinstance(left, DataError):
            return left
        right = self.child[1].eval_ast(data_list, context)
        if isinstance(right, DataError):
            return right
        return self.eval_fun(left, right)

    @staticmethod
    def eval_fun(left, right):
        raise NotImplementedError()  # pure virtual


# Ast classes for the actual binary operation that we support in our language come here.

class AST_Sum(AST_BinOp):
    typedesc = '+'

    @staticmethod
    def eval_fun(left, right):
        return left + right


class AST_Sub(AST_BinOp):
    typedesc = '-'

    @staticmethod
    def eval_fun(left, right):
        return left - right


class AST_Mult(AST_BinOp):
    typedesc = '*'

    @staticmethod
    def eval_fun(left, right):
        return left * right


class AST_Div(AST_BinOp):
    typedesc = '/'

    @staticmethod
    def eval_fun(left, right):
        return left / right


class AST_IDiv(AST_BinOp):
    typedesc = '//'

    @staticmethod
    def eval_fun(left, right):
        return left // right


class AST_Mod(AST_BinOp):
    typedesc = '%'

    @staticmethod
    def eval_fun(left, right):
        return left % right


class AST_Equals(AST_BinOp):
    typedesc = '=='

    @staticmethod
    def eval_fun(left, right):
        return left == right


class AST_NEquals(AST_BinOp):
    typedesc = '!='

    @staticmethod
    def eval_fun(left, right):
        return left != right


class AST_GTE(AST_BinOp):
    typedesc = '>='

    @staticmethod
    def eval_fun(left, right):
        return left >= right


class AST_GT(AST_BinOp):
    typedesc = '>'

    @staticmethod
    def eval_fun(left, right):
        return left > right


class AST_LTE(AST_BinOp):
    typedesc = '<='

    @staticmethod
    def eval_fun(left, right):
        return left <= right


class AST_LT(AST_BinOp):
    typedesc = '<'

    @staticmethod
    def eval_fun(left, right):
        return left < right


# for container[index] expressions.
class AST_GetItem(AST_BinOp):
    typedesc = 'GetItem'

    @staticmethod
    def eval_fun(container, index):
        return container[index]


# AST_And is not derived from AST_BinOp because of short-circuiting.
class AST_And(AST):
    typedesc = 'AND'

    def eval_ast(self, data_list, context):
        left = self.child[0].eval_ast(data_list, context)
        if (not left) or isinstance(left, DataError):
            return left
        return self.child[1].eval_ast(data_list, context)


class AST_Or(AST):  # Not derived from AST_BinOp because of short-circuiting.
    typedesc = 'OR'

    def eval_ast(self, data_list, context):
        left = self.child[0].eval_ast(data_list, context)
        if left:  # including DataError objects.
            return left
        return self.child[1].eval_ast(data_list, context)


class AST_Not(AST):
    typedesc = 'NOT'

    def eval_ast(self, data_list, context):
        arg = self.child[0].eval_ast(data_list, context)
        if isinstance(arg, DataError):
            return arg
        return not arg


# COND(condition, a, b) == condition ? a : b in the C programming language and encodes an if.
# except for the error handling: if cond causes an error, the result is that error.
# Otherwise, only one of a and b is evaluated (so an error in the non-evaluated branch is ignored)
class AST_Cond(AST):
    typedesc = 'COND'

    def eval_ast(self, data_list, context):
        cond = self.child[0].eval_ast(data_list, context)
        if isinstance(cond, DataError):
            return cond
        if cond:
            return self.child[1].eval_ast(data_list, context)
        else:
            return self.child[2].eval_ast(data_list, context)


class AST_Literal(AST):
    """ Abstract syntax tree object (leaf) for literals of arbitrary type.
        The literal object itself is stored in self.value
    """
    typedesc = 'Literal'
    needs_env = _EMPTYSET  # every object has this set as well, actually.

    def __init__(self, val):
        super().__init__(needs_env=self.__class__.needs_env)
        self.value = val

    def __str__(self):
        return self.typedesc + '(' + str(self.value) + ')'

    # noinspection PyUnusedLocal
    def eval_ast(self, data_list, context):
        return self.value


class AST_Lookup(AST):
    """ Abstract syntax tree object (leaf) for lookups in data_list (e.g. attr.strength)
        The name of the entry to look up is stored in self.name
    """
    typedesc = 'Lookup'
    needs_env = _EMPTYSET  # every object has this as well.

    def __init__(self, name: str):
        super().__init__(needs_env=self.__class__.needs_env)
        self.name = name

    def __str__(self):
        return self.typedesc + '(' + str(self.name) + ')'

    def eval_ast(self, data_list, context):
        return data_list.get(self.name)


class AST_IndirectLookup(AST):
    """ Abstract syntax tree object (node) for indirect lookup GET(str), where str is an AST itself
        This is different from AST_Lookup due to error handling and where in the processing parsing occurs.
    """
    typedesc = 'Indirect Lookup'
    needs_env = _EMPTYSET

    def __init__(self, arg: AST):
        assert isinstance(arg, AST)
        super().__init__(needs_env=self.__class__.needs_env)
        self.indirect_arg = arg

    def eval_ast(self, data_list, context):
        name = self.indirect_arg.eval_ast(data_list, context)
        if not isinstance(name, str):
            raise CGEvalException('Argument to GET does not evaluate to a string')
        if not re_key_any.fullmatch(name):
            raise CGEvalException('Argument ' + name + ' to GET is not a valid key')
        return data_list.get(name)


class AST_Funcname(AST):
    """ Abstract syntax tree object (leaf) for lookup of function name (e.g. LIST)
        The name of the looked up function is stored in self.funcname.

        Note that for the user, keywords and function names are mostly indistinguishable except that the user may
        overwrite *some* functions.
    """
    typedesc = 'Function Name'
    needs_env = _EMPTYSET  # set in every object

    def __init__(self, funcname: str):
        super().__init__(needs_env=self.__class__.needs_env)
        self.funcname = funcname

    def __str__(self):
        return self.typedesc + '(' + str(self.funcname) + ')'

    def eval_ast(self, data_list, context):
        return data_list.get(self.funcname, locator=data_list.find_function(self.funcname.lower()))

# We might actually parse core_constants as Literals (of type e.g. function) rather than doing this at
# the evaluation stage. Note, however, that this would make serializing ASTs more difficult.
class AST_CoreConstant(AST):
    typedesc = 'Core Constant'
    needs_env = _EMPTYSET

    def __init__(self, name: str):
        super().__init__(needs_env=self.__class__.needs_env)
        self.name = name

    def __str__(self):
        return self.typedesc + '(' + str(self.name) + ')'

    def eval_ast(self, data_list, context):
        return core_constants[self.name]

class AST_Argname(AST):
    """ Abstract syntax tree object (leaf) for variables (e.g. $a appearing in a function FUN[$a]($a*$a) or $Name.
        The name of the variable in stored in self.argname. We do not need to distinguish externally provided
        variables $Name, $Query and internally used ones such as $a.
    """
    typedesc = 'Argument'

    def __init__(self, argname: str, needs_env=_EMPTYSET):
        self.argname = argname
        super().__init__(needs_env=needs_env)

    def __str__(self):
        return self.typedesc + '(' + str(self.argname) + ')'

    def eval_ast(self, data_list, context: dict):
        # Because we track free variables when constructing ASTs, missing variables should be caught when
        # constructing ASTs rather than at evaluation time.
        # So KeyError exceptions here should not occur from bad input, but indicate bugs.
        return context[self.argname]


class AST_Auto(AST):
    """ Abstract syntax tree object (leaf) for $AUTO, $AUTOQUERY, $AQ.
        The $AUTO vs $AUTOQUERY variant only differ in self.queryname.

        eval_ast works as follows: We can (always) get a list of remaining lookup candidates inside data_list
        as a special variable in context. So we only need to make a new query while explicitly providing the list
        of remaining lookup candidates rather than letting it be generated by the lookup rules (data_list.get supports
        this). The new query name is either the original $Query or $Name, depending on whether we use $AUTOQUERY or
        $AUTO. This is stored in self.queryname
    """
    typedesc = 'Auto'

    def __init__(self, queryname: str):
        super().__init__(needs_env={CONTINUE_LOOKUP, queryname})
        self.queryname = queryname

    def eval_ast(self, data_list, context: dict):
        return data_list.get(context[self.queryname], locator=context[CONTINUE_LOOKUP])


class AST_FunctionCall(AST):
    """ Abstract syntax tree (inner node) for function calls. First child is function object (more precisely, an AST
        that evaluates to one). The remaining children are the arguments ASTs. The children ASTs have special flags set
        to determine the *-ed-ness and binding type.
    """
    typedesc = 'Call'

    def eval_ast(self, data_list, context: dict):
        fun = self.child[0].eval_ast(data_list, context)
        if isinstance(fun, DataError):
            return fun
        # build list and dict of keyword and positional arguments
        posargs = []
        kwargs = {}
        for arg in self.child[1:]:
            a = arg.eval_ast(data_list, context)
            if isinstance(a, DataError):
                return a
            if arg.argtype is _FUNARG_EXP:  # normal positional argument f(1)
                posargs.append(a)
            elif arg.argtype is _FUNARG_STAREXP:  # list-unpacked *-argument f(*posargs)
                posargs += a
            elif arg.argtype is _FUNARG_STARSTAREXP:  # dict-unpacked kw-argument f(**kwargs)
                kwargs.update(**a)
            else:
                assert arg.argtype is _FUNARG_NAMEVAL  # keyword-argument f(blah = "foo")
                kwargs[arg.namebind] = a
        return fun(*posargs, **kwargs)


# Lambdas
class AST_Lambda(AST):
    """ Abstract syntax tree (inner node) for function definitions. These always have 2 children. The first child
        encodes the list of expected variables, the second is the function body. Note that the function body is an AST,
        whereas the list of expected variables is not.
    """

    typedesc = 'Lambda'

    def __init__(self, expected_args: list, body: AST):
        """
        construct a new lambda
        :param expected_args: list of tuples (name, type [,default-value]) for the arguments.
                              type encodes the *-ed-ness and whether a default is present
        :param body: function body as AST
        """

        # needs_env determines the set of free variables. This is the set of variables that occur in the body, but are
        # not in the argument list (this can happen due to special args like $Name or nested lambdas).
        # We have to take care that default arguments can bring in new free variables.
        # By going backwards and removing before adding, we ensure means that
        # lambdas such as FUN[$c,$d]( FUN[$a, $b=$a, $c=$c]($a+$b+$c+$d) ) work out correctly:
        # $b = $a will default $b to the first positional argument
        # (In eval_ast, we assign the new local context from left to right and evaluate defaults with the new
        # local context)
        # $c = $c will default the inner $c to the outer $c
        # Note that special args like $Name, $Query in the body or as default args refer to the definition context.
        needs_env = set(body.needs_env)
        for arg in reversed(expected_args):
            needs_env.discard(arg[0])  # arg[0] may be None. In this case, this does nothing.
            if arg[1] is _ARGTYPE_DEFAULT:
                needs_env |= arg[2].needs_env

        super().__init__(expected_args, body, needs_env=needs_env)

    def eval_ast(self, data_list, context: dict):
        # self.child[0] is a list of pairs (name, type) or triples (name, type, defaultarg) for the variable names:
        # name is a string denoting the actual name (or None for *)
        # type is a string constant set to _ARGTYPE_FOO to differentiate
        # name, name = default, *, *name and **name
        # self.child[1] is an AST for the actual function body.
        # As opposed to Python proper, it does not matter much when we evaluate default arguments,
        # because we can't mutate anyway.
        # We choose to evaluate at (each) call, if actually needed.
        # This means that unused invalid default arguments do not trigger errors and that we can use previous argument
        # values as defaults: LAMBDA[$a, $b=$a](...)
        # Special args like $Name in default arguments or the body bind to the value at lambda definition,
        # because we capture old_context.

        # We return a function that captures the local variables expectedargs, body and old_context.
        # (i.e. the returned function object contains references to data_list, body, and to a copy of context)
        # We assume that during the lifetime of the returned function, the passed arguments data_list does not change.
        expectedargs = self.child[0]
        # expectedargs is a list of tuples ($name, $type [, default-value] ) of the arguments that the function expects
        body = self.child[1]

        # We (shallow) copy the given context at time of lambda definition. This is needed, because the
        # caller might mutate context later. This is a bit inconsistent with data_list, but we can't really copy that
        # due to efficiency. We need to assume there that the passed data_list and the entries of context are not
        # mutated during the lifetime of the resulting lambda.

        old_context = dict(context)

        def fun(*funargs, **kwargs):
            new_context = dict(old_context)  # shallow copy should be OK. We do not modify new_context[key] values
            # As opposed to above, this copy is done for each lambda evaluation.
            funargpos = 0  # index of next funarg that has not yet been assigned to an expected argument
            funarglen = len(funargs)  # number of positional arguments that we actually got
            kwargonly = False  # set to true after we encounter a * (in the arguments in the lambda def)
            for arg in expectedargs:  # expectedargs ist the list of arguments in the lambda's definition. All of
                # these need to be assigned in new_context.
                if arg[1] is _ARGTYPE_NORMAL or arg[1] is _ARGTYPE_DEFAULT:  # non-starred argument in lambda def
                    if arg[0] in kwargs:  # argument is given as a keyword-argument
                        # Note that modifying kwargs does not mutate anything at the call site:
                        # def fun(**D):
                        #     del D['foo']
                        # D = {'foo':'bar'}
                        # fun(**D) will not modify D.
                        new_context[arg[0]] = kwargs.pop(arg[0])
                        if funargpos != funarglen:
                            raise AttributeError("keyword argument used before (expected or given) positional argument")
                    elif funargpos < funarglen:  # Still have positional arguments given to fun left. We take the next.
                        new_context[arg[0]] = funargs[funargpos]
                        funargpos += 1
                    elif arg[1] is _ARGTYPE_NORMAL:
                        if kwargonly:
                            raise AttributeError("Missing Keyword-only argument $" + arg[0])
                        else:
                            raise AttributeError("Missing positional argument $" + arg[0])
                    else:  # arg[1] is _ARGTYPE_DEFAULT, not given as keyword, no more positional arguments given.
                        defaultarg = arg[2].eval_ast(data_list, new_context)  # We need to use new_context here
                        if isinstance(defaultarg, DataError):
                            return defaultarg
                        new_context[arg[0]] = defaultarg
                elif arg[1] is _ARGTYPE_STAR:
                    kwargonly = True
                    if funargpos != funarglen:
                        raise AttributeError("too many positional arguements")
                elif arg[1] is _ARGTYPE_STARARG:  # *$arg is guaranteed to be the last arg in expectedargs
                    new_context[arg[0]] = funargs[funargpos:]  # assign $arg to the remaining positional args given
                    funargpos = funarglen
                    kwargonly = True
                else:
                    assert arg[1] is _ARGTYPE_KWARGS
                    new_context[arg[0]] = kwargs  # kwargs that matched required positionals have been popped before.
                    kwargs = {}
            if len(kwargs) > 0:
                raise AttributeError("Unknown keyword argument $" + next(iter(kwargs.keys())))
            if funargpos != funarglen:
                raise AttributeError("Too many positional arguments")
            return body.eval_ast(data_list, new_context)

        return fun

class AST_List(AST):
    typedesc = 'List'
    # default init does The Right Thing (TM): self.child is a tuple of child AST objects.
    def eval_ast(self, data_list: 'CharVersion.CharVersion', context: dict):
        ret = []
        for c in self.child:
            c_eval = c.eval_ast(data_list, context)
            if isinstance(c_eval, DataError):
                return c_eval
            ret.append(c_eval)
        return ret

class AST_Dict(AST):
    typedesc = 'Dict'
    # default init does The Right Thing (TM)
    def eval_ast(self, data_list: 'CharVersion.CharVersion', context: dict):
        assert len(self.child) % 2 == 0
        ret = {}
        it = iter(self.child)
        while True:
            try:
                c_kw = next(it)
            except StopIteration:
                break
            c_kw = c_kw.eval_ast(data_list, context)
            if isinstance(c_kw, DataError):
                return c_kw
            c_val = next(it).eval_ast(data_list, context)
            if isinstance(c_val, DataError):
                return c_val
            ret[c_kw] = c_val
        return ret

class AST_Set(AST):
    typedesc = 'Set'
    def eval_ast(self, data_list: 'CharVersion.CharVersion', context: dict):
        ret = []
        for c in self.child:
            c_eval = c.eval_ast(data_list, context)
            if isinstance(c_eval, DataError):
                return c_eval
            ret.append(c_eval)
        return frozenset(ret)

start = 'root_expression'  # start is used by PLY yacc to determine the BNF roof.

# order of precedence and associativity of operations. Ambiguous cases will produce errors.
precedence = (
    ('right', 'OR'),
    ('right', 'AND'),
    ('right', 'NOT'),
    ('nonassoc', 'LTE', 'GTE', '<', '>', 'EQUALS', 'NEQUALS'),
    ('left', '+', '-'),
    ('left', '*', '/', '%', 'IDIV'),
)


# noinspection PyUnusedLocal
def p_error(p):
    raise CGParseException


# root_expression serves as a hook for "done with parsing". This does not actually create an extra tree node.
# noinspection PySingleQuotedDocstring
def p_root(p):
    "root_expression : expression"
    p[0] = p[1]
    if not p[0].needs_env <= _ALLOWED_SPECIAL_ARGS:  # <= means subset here.
        raise CGParseException("Unbound variables $" + ", $".join(_ALLOWED_SPECIAL_ARGS - p[0].needs_env))


# noinspection PySingleQuotedDocstring
def p_expression_bracket(p):
    "expression : '(' expression ')' "
    p[0] = p[2]


# noinspection PySingleQuotedDocstring
def p_expression_literal(p):
    """expression : STRING
                  | FLOAT
                  | INT"""
    p[0] = AST_Literal(p[1])

# noinspection PySingleQuotedDocstring
def p_coreconstant(p):
    "expression : CORECONSTANT"
    p[0] = AST_CoreConstant(p[1])

# noinspection PySingleQuotedDocstring
# def p_expression_true(p):
#     "expression : TRUE"
#     p[0] = AST_Literal(True)


# noinspection PySingleQuotedDocstring
# def p_expression_false(p):
#     "expression : FALSE"
#     p[0] = AST_Literal(False)


# noinspection PySingleQuotedDocstring
def p_expression_sum(p):
    "expression : expression '+' expression"
    p[0] = AST_Sum(p[1], p[3])


# noinspection PySingleQuotedDocstring
def p_expression_sub(p):
    "expression : expression '-' expression"
    p[0] = AST_Sub(p[1], p[3])


# noinspection PySingleQuotedDocstring
def p_expression_mult(p):
    "expression : expression '*' expression"
    p[0] = AST_Mult(p[1], p[3])


# noinspection PySingleQuotedDocstring
def p_expression_div(p):
    "expression : expression '/' expression"
    p[0] = AST_Div(p[1], p[3])


# noinspection PySingleQuotedDocstring
def p_expression_idiv(p):
    "expression : expression IDIV expression"
    p[0] = AST_IDiv(p[1], p[3])


# noinspection PySingleQuotedDocstring
def p_expression_modulo(p):
    "expression : expression '%' expression"
    p[0] = AST_Mod(p[1], p[3])


# noinspection PySingleQuotedDocstring
def p_expression_equals(p):
    "expression : expression EQUALS expression"
    p[0] = AST_Equals(p[1], p[3])


# noinspection PySingleQuotedDocstring
def p_expression_nequals(p):
    "expression : expression NEQUALS expression"
    p[0] = AST_NEquals(p[1], p[3])


# noinspection PySingleQuotedDocstring
def p_expression_gt(p):
    "expression : expression '>' expression"
    p[0] = AST_GT(p[1], p[3])


# noinspection PySingleQuotedDocstring
def p_expression_gte(p):
    "expression : expression GTE expression"
    p[0] = AST_GTE(p[1], p[3])


# noinspection PySingleQuotedDocstring
def p_expression_lt(p):
    "expression : expression '<' expression"
    p[0] = AST_LT(p[1], p[3])


# noinspection PySingleQuotedDocstring
def p_expression_lte(p):
    "expression : expression LTE expression"
    p[0] = AST_LTE(p[1], p[3])


# noinspection PySingleQuotedDocstring
def p_expression_and(p):
    "expression : expression AND expression"
    p[0] = AST_And(p[1], p[3])


# noinspection PySingleQuotedDocstring
def p_expression_or(p):
    "expression : expression OR expression"
    p[0] = AST_Or(p[1], p[3])


# noinspection PySingleQuotedDocstring
def p_expression_not(p):
    "expression : NOT expression"
    p[0] = AST_Not(p[2])


# noinspection PySingleQuotedDocstring
def p_expression_cond(p):
    "expression : COND '(' expression ',' expression ',' expression ')'"
    p[0] = AST_Cond(p[3], p[5], p[7])


#noinspection PySingleQuotedDocstring
def p_expression_cond_if_then_else(p):
     "expression : IF expression THEN expression ELSE expression"
     p[0] = AST_Cond(p[2], p[4], p[6])


# noinspection PySingleQuotedDocstring
def p_expression_funname(p):
    "expression : FUNCNAME"
    p[0] = AST_Funcname(p[1])


# noinspection PySingleQuotedDocstring
def p_expression_name(p):
    "expression : LOOKUP"
    p[0] = AST_Lookup(p[1])


# noinspection PySingleQuotedDocstring
def p_expression_get(p):
    "expression : GET '(' expression ')'"
    p[0] = AST_IndirectLookup(p[3])


# noinspection PySingleQuotedDocstring
def p_expression_variable(p):
    "expression : ARGNAME"
    p[0] = AST_Argname(p[1], needs_env=frozenset({p[1]}))


# noinspection PySingleQuotedDocstring
def p_expression_specialarg(p):
    "expression : SPECIALARG"
    p[0] = AST_Argname(p[1], needs_env=frozenset({p[1]}))


# noinspection PySingleQuotedDocstring
def p_expression_auto(p):
    "expression : AUTO"
    p[0] = AST_Auto(p[1])


# p_argument turns an expression exp into a function argument, e.g. for use in f(exp)
# To be consistent with Python, function arguments can be of the form
# exp, *exp, **exp, $name=exp
# We do not wrap exp (and possibly name) into one of 4 different AST_FOO - types.
# The reason is that eval_ast could not do anything meaningful:
# If exp = [1, 2], then the corresponding hypothetical AST_STARRED_EXP(exp).eval_ast(...)
# must NOT return the tuple 1, 2, since then for a function g(a,b) with
# arguments a,b, g(*exp) would bind a to the tuple (1,2) and leave b unbound...
# In fact, *exp is not a valid Python expression in most contexts.
# The unpacking and the function call have to be handled simultaneously and we just mark the arguments.
# the p[0].typedesc = ... assignments are just for debugging and printing.
# Note that p[0].typedesc on the left-hand side is an instance variable, the right-hand side a class variable!
# p[0].typedesc += "..." would actually work and create an instance variable because python is weird.

# types of arguments appearing in function calls f(...)
_FUNARG_EXP = 'expression'  # f(x)
_FUNARG_STAREXP = '*expression'  # f(*list)
_FUNARG_STARSTAREXP = '**expression'  # f(**dict)
_FUNARG_NAMEVAL = 'named argument'  # f(name = x)


# noinspection PySingleQuotedDocstring
def p_argument_exp(p):
    "argument : expression"
    p[0] = p[1]
    p[0].argtype = _FUNARG_EXP


# noinspection PySingleQuotedDocstring
def p_argument_listexp(p):
    "argument : '*' expression"
    p[0] = p[2]
    p[0].argtype = _FUNARG_STAREXP
    p[0].typedesc = '*' + p[0].typedesc  # this creates an instance variable


# noinspection PySingleQuotedDocstring
def p_argument_dictexp(p):
    "argument : '*' '*' expression"
    p[0] = p[3]
    p[0].argtype = _FUNARG_STARSTAREXP
    p[0].typedesc = '**' + p[0].typedesc  # this creates an instance variable


# noinspection PySingleQuotedDocstring
def p_argument_nameval(p):
    "argument : ARGNAME '=' expression"
    p[0] = p[3]
    p[0].argtype = _FUNARG_NAMEVAL
    p[0].namebind = p[1]
    p[0].typedesc = p[0].typedesc + ' bound to ' + p[0].namebind  # += actually would work (which I find strange)

# noinspection PySingleQuotedDocstring
def p_argument_nameval_as_string(p):
    "argument : STRING '=' expression"
    p[0] = p[3]
    p[0].argtype = _FUNARG_NAMEVAL
    p[0].namebind = p[1]
    p[0].typedesc = p[0].typedesc + ' bound to ' + p[0].namebind

def p_arglist(p):
    """arglist :
               | arglist_nonempty
               | arglist_nonempty ','"""
    if len(p) == 1:
        p[0] = []
    else:
        p[0] = p[1]


def p_arglist_nonempty(p):
    """arglist_nonempty : argument
                        | arglist_nonempty ',' argument"""
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = p[1] + [p[3]]

def p_expressionlist_nonempty(p):
    """expressionlist_nonempty : expression
                               | expressionlist_nonempty ',' expression"""
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = p[1] + [p[3]]

def p_list(p):
    """expression : '[' ']'
                  | '[' expressionlist_nonempty ']'
                  | '[' expressionlist_nonempty ',' ']'"""
    if len(p) == 3:
        p[0] = AST_List()
    else:
        p[0] = AST_List(*p[2])

def p_dictlist_nonempty(p):
    """dictlist_nonempty : expression ':' expression
                         | dictlist_nonempty ',' expression ':' expression"""
    if len(p) == 4:
        p[0] = [p[1], p[3]]
    else:
        p[0] = p[1] + [p[3], p[5]]

def p_dict(p):
    """expression : '{' '}'
                  | '{' dictlist_nonempty '}'
                  | '{' dictlist_nonempty ',' '}'"""
    if len(p) == 3:
        p[0] = AST_Dict()
    else:
        p[0] = AST_Dict(*p[2])

def p_set(p):
    """expression : '{' expressionlist_nonempty '}'
                  | '{' expressionlist_nonempty ',' '}'"""
    p[0] = AST_Set(*p[2])

# noinspection PySingleQuotedDocstring
def p_function_call(p):
    "expression : expression '(' arglist ')'"
    # keyword arguments must come after positional arguments :
    kwonly = False
    for arg in p[3]:
        if arg.argtype is _FUNARG_STARSTAREXP or arg.argtype is _FUNARG_NAMEVAL:
            kwonly = True
        elif kwonly:
            raise CGParseException("Positional arguments must not follow keyword arguments")
    p[0] = AST_FunctionCall(p[1], *p[3])


# noinspection PySingleQuotedDocstring
def p_getitem(p):
    "expression : expression '[' expression ']'"
    p[0] = AST_GetItem(p[1], p[3])


_ARGTYPE_NORMAL = 'Arg'  # def f(x)
_ARGTYPE_DEFAULT = 'Defaulted Argument'  # def f(x=5)
_ARGTYPE_STAR = 'End of Positional Arguments'  # def f(*)
_ARGTYPE_STARARG = 'Rest of Positional Arguments'  # def f(*arg)
_ARGTYPE_KWARGS = 'Rest of Keyword Arguments'  # def (f**kwargs)


# noinspection PySingleQuotedDocstring
def p_declarg_name(p):
    "declarg : ARGNAME"
    p[0] = (p[1], _ARGTYPE_NORMAL)


# noinspection PySingleQuotedDocstring
def p_declarg_defaulted_name(p):
    "declarg : ARGNAME '=' expression"
    p[0] = (p[1], _ARGTYPE_DEFAULT, p[3])


# noinspection PySingleQuotedDocstring
def p_declarg_pos_end(p):
    "declarg : '*'"
    p[0] = (None, _ARGTYPE_STAR)


# noinspection PySingleQuotedDocstring
def p_declarg_pos_rest(p):
    "declarg : '*' ARGNAME"
    p[0] = (p[2], _ARGTYPE_STARARG)


# noinspection PySingleQuotedDocstring
def p_declarg_kw_rest(p):
    "declarg : '*' '*' ARGNAME"
    p[0] = (p[3], _ARGTYPE_KWARGS)


def p_declarg_list(p):
    """declarglist :
                    | declarglist_nonempty"""
    if len(p) == 1:
        p[0] = []
    else:
        p[0] = p[1]
    if len(p[0]) != len(set(x[0] for x in p[0])):
        raise CGParseException("Duplicate argument used in function definition")


def p_declarglist_nonempty(p):
    """declarglist_nonempty : declarg
                            | declarglist_nonempty ',' declarg"""
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = p[1] + [p[3]]


# noinspection PySingleQuotedDocstring
def p_functiondef(p):
    "expression : FUN '[' declarglist ']' '(' expression ')'"
    args = p[3]
    # Check validity of argument list : There are restrictions on the order of argument types
    # (kw-arguments after positional arguments etc
    seen_default = False
    seen_restkw = False
    seen_end = False
    for arg in args:
        if seen_end:
            raise CGParseException("Arguments after end of kwargs")
        if arg[1] is _ARGTYPE_NORMAL:  # normal argument $a
            if seen_default and not seen_restkw:
                raise CGParseException("positional arg after defaulted arg")
        elif arg[1] is _ARGTYPE_DEFAULT:  # defaulted argument $a = 1
            seen_default = True
        elif (arg[1] is _ARGTYPE_STAR) or (arg[1] is _ARGTYPE_STARARG):  # end of positional arguments * or *$a
            if seen_restkw:
                raise CGParseException("taking rest of positional arguments multiple times")
            seen_restkw = True
        elif arg[1] is _ARGTYPE_KWARGS:  # **$kwargs must be last
            seen_end = True
        else:
            assert False
    p[0] = AST_Lambda(args, p[6])  # Note that p[3] is a list, which is NOT unpacked here. p[6] is the body.


parser = yacc.yacc()


def input_string_to_value(input_string: str) -> Union[int, float, str, AST, DataError, None]:
    """
        Parses an input string that a user inputs and parses it either as a string, a number or a formula,
        depending on whether it starts/ends with =, ", '
        This is the 'default' interface to the parses.
        Note that in some context, we may need to have a slightly different input format due to (un)escaping,
        so we will need some other functions for other input data formats.

        Returns either an int, string, float, AST (parsed formula), or a DataError object (for mis-parses) or None (for
        the empty input string).
    """
    if len(input_string) == 0:
        return None
    # "STRING or "STRING" or 'STRING or 'STRING' all parse as strings as well as STRING (the latter is handled below
    # if no other rules match)
    if input_string[0] == '"' or input_string[0] == "'":
        if input_string[-1] == input_string[0]:
            return input_string[1:-1]
        else:
            return input_string[1:]
    elif input_string[0] == '=':  # everything starting with = is a formula, with the = itself not part of it
        try:
            result = parser.parse(input_string[1:])
        except (SyntaxError, CGParseException) as e:  # TODO: better error handling
            result = DataError(exception=e)  # TODO: Capture exception? (very expensive)
        return result
    elif re_number_int.fullmatch(input_string):
        return int(input_string)
    elif re_number_float.fullmatch(input_string):
        return float(input_string)
    else:
        return input_string


# for debugging only.
if __name__ == '__main__':
    lex.runmain()
