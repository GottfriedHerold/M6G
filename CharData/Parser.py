import ply.lex as lex
import ply.yacc as yacc
from ply.lex import TOKEN
# list of tokens (excluding literals):
from .Regexps import re_key_any, re_number_float, re_number_int, re_argname, re_funcname, re_special_arg
from .CharExceptions import DataError, CGParseException
from .CharVersion import CharVersion

keywords = [
    'COND',
    'OR',
    'AND',
    'NOT',
    'FUN',  # alternative: LAMBDA is also recognized
    'TRUE',
    'FALSE',
]

# $Name tokens, where Name starts with a capital letter will be recognized iff(!) Name.upper() is in this dict.

special_args = {
    # keys are what is recognized as $Key (after uppercasing, so keys need to be capitalized here).
    # values are triples (TOKEN, Value, Args) to mean that this gets parsed as a token TOKEN with value Value.
    # TOKEN needs to be in the tokens list. Value is the value seen by a propagated by the AST browser. In particular,
    # for TOKEN == 'ARGNAME', Value determines which variable is looked up from the context dict in eval_ast, i.e.
    # under which name the binding is supplied by the external caller.
    # Values for these special arguments should begin with a capital letter in order to be from a set of names disjoint
    # from internal user-provided variables used in lambdas.
    # Args denotes the set of Values that are used during evaluation and that get union'ed into needs_env.

    # TODO: AUTO and AUTOQUERY spec

    'A': ('AUTO', 'A', frozenset()),  # $AUTO evaluates to whatever it would, if the AST was empty and it was queried directly.
    'AUTO': ('AUTO', 'AUTO', frozenset()),
    'Q': ('ARGNAME', 'Query', {'Query'}),  # $QUERY is the query string, usually equals to $NAME. Its presence needs special treatment.
    'AQ': ('AUTOQUERY', 'AQ', {'Query'}),  # $AUTOQUERY evaluates to whatever it would if the AST was empty and it was queried as $QUERY
    'AUTOQUERY': ('AUTOQUERY', 'AUTOQUERY', {'Query'}),
    'QUERY': ('ARGNAME', 'Query', {'Query'}),
    'NAME': ('ARGNAME', 'Name', {'Name'}),  # $Name is set by the caller. It does not actually need special treatment here (apart from beginning  with a capital)
}

tokens = [
    'STRING',     # Quote - enclosed string
    'IDIV',       # // (integral division, as opposed to /, which gives floats)
    'INT',        # Integer
    'FLOAT',      # Floats
    'FUNCNAME',   # FUNCTION (all - caps)
    'LOOKUP',     # attr.strength
    'EQUALS',     # == (equality comparison)
    'NEQUALS',    # != (inequality comparison)
    'LTE',        # <=
    'GTE',        # >=
    'ARGNAME',    # $argument
    'AUTO',       # $A[uto] - gets default value
    # 'QUERY',    # $Q[uery] - query string
    'AUTOQUERY',  # $AUTOQUERY - gets default value for original query string
    'NEEDSENV',   # fictious token that gets generated at the end by the lexer and contains information on whether certain special tokens appear.
                  # A final parser rule expression :== expression NEEDSENV then collects this and passes this on to the caller.
                  # This is a bit more efficient than propagating needs_env through the AST tree.
] + keywords
literals = "+-*/%()[],<>="

# Note: Order matters!
# Function defs come first (in order of definition), then t_TOKEN = regexp defs (in order of decreasing length of regexp)
# then literals


def t_STRING(token):  # strings delimited by either ' or "
    r"(?:'[^']*')|" r'(?:"[^"]*")'  # Allow either ' or " as delimeters (Python-like)
    token.value = token.value[1:-1]  # strip the quotation marks already by the lexer
    return token

@TOKEN(re_number_float.pattern)  # floating numbers with a .
def t_FLOAT(token):
    token.value = float(token.value)
    return token

# This must come after t_FLOAT (so that the prefix "5" of 5.4 is not parsed as an int)
@TOKEN(re_number_int.pattern)  # integers
def t_INT(token):
    token.value = int(token.value)
    return token

# This is a single rule for
# -Keywords OR AND NOT etc
# -Functions FUNC
# Special References $Name etc.
# local variables $name
# references to other data fields .attr.strength
# This is included in a single t_WORD in order to ensure that strings such as Ab do not parse as separate tokens A b
# This way we get an error instead of a mis-parse.
def t_WORD(token):
    r"[$]?[a-z._A-Z]+"
    if re_special_arg.fullmatch(token.value):  # r"[$][A-Z][a-zA-Z_]*"
        try:
            spec = special_args[token.value[1:].upper()]
        except KeyError:
            token.lexer.needs_env = set()
            raise SyntaxError("Invalid argument name $" + token.value)
        else:
            token.type = spec[0]
            token.value = spec[1]
            token.lexer.needs_env |= spec[2]
    elif re_argname.fullmatch(token.value):  # r"[$][a-z_]+"
        token.type = 'ARGNAME'
        token.value = token.value[1:]  # strip leading $
    elif re_funcname.fullmatch(token.value):  # "[A-Z]+"  -- No underscores for now
        token.type = 'FUNCNAME'
        if token.value in keywords:
            token.type = token.value
        if token.value == 'LAMBDA':
            token.type = 'FUN'
    elif re_key_any.fullmatch(token.value):  # complicated regexp, matching lookups attr.strength etc.
        token.type = 'LOOKUP'
    else:
        token.lexer.needs_env = set()
        raise SyntaxError("Did not recognize String " + token.value)
    return token


# def t_ARGNAME(token):
#     r"[$][a-z_]+"
#     token.value = token.value[1:]
#     return token
#
# def t_SPECIALARGS(token):
#     r"[$][A-Z][a-zA-Z_]*"
#     token.value = token.value[1:].upper()
#     if token.value in special_args:
#         spec = special_args[token.value]
#         token.type = spec[0]
#         token.value = spec[1]
#         if spec[1] is not None:
#             token.lexer.needs_env |= {spec[1]}
#         return token
#     else:
#         token.lexer.needs_env = set()
#         raise SyntaxError("Invalid argument name $" + token.value)

# # keywords and the like
# def t_FUNCNAME(token):
#     r"[A-Z]+"  # No underscores for now
#     if token.value in keywords:
#         token.type = token.value
#     if token.value == 'LAMBDA':
#         token.type = 'FUN'
#     return token

# reference to other data field
# @TOKEN(re_key_any.pattern)
# def t_LOOKUP(token):
#     return token


# triggered at end of parse string.
# If lexer.needs_env != {}, we generate a new token of type 'NEEDSENV' that contains the needs_env information.
# After this is processed, t_eof is called again, but this time with lexer.needs_env == {}. Returning None ends parsing.
def t_eof(token):
    if token.lexer.needs_env != set():
        r = lex.LexToken()
        r.type = 'NEEDSENV'
        r.value = token.lexer.needs_env
        r.lineno = 0
        r.lexpos = 0
        token.lexer.needs_env = set()
        return r
    else:
        return None

def t_error(token):
    token.lexer.needs_env = set()
    token.lexer.input("")
    raise SyntaxError("Could not parse formula")

t_ignore = ' \t\n\r\f\v'  # ignore (ASCII) whitespace

t_IDIV = r"//"
t_EQUALS = r"=="
t_NEQUALS = r"!="
t_LTE = r"<="
t_GTE = r">="

lexer = lex.lex()
lexer.needs_env = set()

# We parse the input string into an abstract syntax tree object.
# (non-leaf nodes correspond to operations, children to operands, leafs to literals)
# This is an instance of a class (derived from) AST, whose
# actual derived class determines the type of object.
# (e.g. AST_Sum for an addition, AST_Mult for a multiplication)
# t's children are stored in t.child[0], ...
# The classvariable typedesc is a string denoting the type of operation.
# It is only used for printing (which in turn is only for debugging)
# AST.eval_ast(instance, data_list, context)
# ASTs are the result from parsing the input string.
# NOTE: The result of parsing is purely a function of the input string. There is no dependency on
# other data sources for the references etc. These dependencies only come into play when actually evaluating.

# To actually evaluate the AST, use instance.eval_ast(data_list, context)
# data_list is the list of data sources, used to evaluate references.
# context is a dict for variables $arg = value that may appear. External caller should only set $Name
# (context is mostly used internally to implement lambdas INSIDE ASTs)


class AST:
    """
    Abstract syntax tree class. Actual objects are from derived classes.

    Use eval_ast(data_list, context) to evaluate the AST.
    For the root node, needs_env contains the set of free variables/dependencies that need to be passed via context.
    """
    typedesc = 'AST'  # for debug printing. Should never be used on parent class.
    needs_env = frozenset()  # default if need_env is never set for a particular object.
    def __init__(self, *kw):
        """Creates an AST Node. Positional arguments are stored as child nodes. These are ASTs except for literals"""
        self.child = kw
    def __str__(self):  # Debug only
        return self.typedesc + '[' + ", ".join([str(x) for x in self.child]) + ']'
    def eval_ast(self, data_list: CharVersion, context: dict):
        """
        evaluates the ast within the given context.
        IMPORTANT: eval_ast can return lambdas which may capture data_list and context possibly *by reference*.
        For data_list, we only ever hand it through, but for context, do not rely on stable behaviour and never modify
        a dict after it is passed to eval_ast for the lifetime of the result.

        :param data_list: List of data sources used for lookups. Of type CharVersion or None.
        :param context: Dict of variables used in evaluations. External callers need to supply those in self.needs_env.
        :return: result of evaluation.
        """
        raise NotImplementedError()  # pure virtual method


class AST_BinOp(AST):
    """
    pure virtual class used for AST nodes of binary operations. eval_fun is used for the actual binary operation.
    This class merely does the error handling common to all binary operations.
    """
    typedesc = 'Binary Op'  # should never be used.
    def eval_ast(self, data_list, context):
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

class AST_And(AST):  # Not derived from AST_BinOp because of short-circuiting.
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
    typedesc = 'Literal'

    # noinspection PyUnusedLocal
    def eval_ast(self, data_list, context):
        return self.child[0]

class AST_Lookup(AST):
    typedesc = 'Lookup'
    def eval_ast(self, data_list, context):
        assert False  # TODO

class AST_Funcname(AST):
    typedesc = 'Function Name'
    def eval_ast(self, data_list, context):
        # TODO: Change? This is only here to simplify debugging
        if self.child[0] == 'LIST':
            return lambda *kw: [*kw]
        if self.child[0] == 'DICT':
            return dict
        assert False

class AST_Argname(AST):
    typedesc = 'Argument'
    def eval_ast(self, data_list, context):
        return context[self.child[0]]  # may raise exception

class AST_Auto(AST):
    typedesc = 'Auto'
    def eval_ast(self, data_list, context):
        assert False  # TODO

class AST_FunctionCall(AST):
    typedesc = 'Call'
    def eval_ast(self, data_list, context):
        fun = self.child[0].eval_ast(data_list, context)
        if isinstance(fun, DataError):
            return fun
        posargs = []
        kwargs = {}
        for arg in self.child[1:]:
            a = arg.eval_ast(data_list, context)
            if isinstance(a, DataError):
                return a
            if arg.argtype is _FUNARG_EXP:
                posargs.append(a)
            elif arg.argtype is _FUNARG_STAREXP:
                posargs += a
            elif arg.argtype is _FUNARG_STARSTAREXP:
                kwargs.update(**a)
            else:
                assert arg.argtype is _FUNARG_NAMEVAL
                kwargs[arg.namebind] = a
        return fun(*posargs, **kwargs)

# Lambdas
class AST_Lambda(AST):
    typedesc = 'Lambda'
    def eval_ast(self, data_list, context: dict):
        # self.child[0] is a list of pairs (name, type) or triples (name, type, defaultarg) for the variable names:
        # name is a string denoting the actual name (or None for *)
        # type is a string constant set to _ARGTYPE_* to differentiate
        # name, name = default, *, *name and **name
        # self.child[1] is an AST for the actual function body.
        # As opposed to Python proper, it does not matter much when we evaluate default arguments, because we can't mutate anyway.
        # We choose to evaluate at (each) call, if actually needed (which means that unused invalid default arguments do not trigger errors)

        # Captures: data_list and context
        expectedargs = self.child[0]
        # expectedargs is a list of tuples ($name, $type [, default-value] ) of the arguments that the function expects
        body = self.child[1]

        # (shallow) copy the context or use a reference.
        # Shallow copy is the "correct" way, but this is inconsistent with the handling of data_list, which we really
        # do not want to copy. I miss C++ r-value references...
        old_context = dict(context)
        def fun(*funargs, **kwargs):
            new_context = dict(old_context)  # shallow copy should be OK. We do not modify new_context[key] values
            funargpos = 0  # index of next funarg that has not yet been assigned to an expected argument
            funarglen = len(funargs)  # number of positional arguments that we actually got
            kwargonly = False
            for arg in expectedargs:
                if arg[1] is _ARGTYPE_NORMAL or arg[1] is _ARGTYPE_DEFAULT:
                    if arg[0] in kwargs:
                        new_context[arg[0]] = kwargs.pop(arg[0])
                        if funargpos != funarglen:
                            raise AttributeError("keyword argument used before (expected or given) positional argument")
                    elif funargpos < funarglen:  # Still have arguments given to fun left
                        new_context[arg[0]] = funargs[funargpos]
                        funargpos += 1
                    elif arg[1] is _ARGTYPE_NORMAL:
                        if kwargonly:
                            raise AttributeError("Missing Keyword-only argument $" + arg[0])
                        else:
                            raise AttributeError("Missing positional argument $" + arg[0])
                    else:
                        defaultarg = arg[2].eval_ast(data_list, context)
                        if isinstance(defaultarg, DataError):
                            return defaultarg
                        new_context[arg[0]] = defaultarg
                elif arg[1] is _ARGTYPE_STAR:
                    kwargonly = True
                    if funargpos != funarglen:
                        raise AttributeError("too many positional arguements")
                elif arg[1] is _ARGTYPE_STARARG:  # guaranteed to be the last arg in expectedargs
                    new_context[arg[0]] = funargs[funargpos:]
                    funargpos = funarglen
                    kwargonly = True
                else:
                    assert arg[1] is _ARGTYPE_KWARGS
                    new_context[arg[0]] = kwargs
                    kwargs = {}
            if len(kwargs) > 0:
                raise AttributeError("Unknown keyword argument $" + next(iter(kwargs.keys())))
            if funargpos != funarglen:
                raise AttributeError("Too many positional arguments")
            return body.eval_ast(data_list, new_context)
        return fun

class AST_GetItem(AST_BinOp):
    typedesc = 'GetItem'
    @staticmethod
    def eval_fun(container, index):
        return container[index]

start = 'expression'
precedence = (
    ('nonassoc', 'NEEDSENV'),
    ('right', 'OR'),
    ('right', 'AND'),
    ('right', 'NOT'),
    ('nonassoc', 'LTE', 'GTE', '<', '>', 'EQUALS', 'NEQUALS'),
    ('left', '+', '-'),
    ('left', '*', '/', '%', 'IDIV'),
)

def p_error(p):
    lexer.needs_env = set()
    raise CGParseException

def p_needsenv(p):
    "expression : expression NEEDSENV"
    p[0] = p[1]
    p[0].needs_env = p[2]


def p_expression_bracket(p):
    "expression : '(' expression ')' "
    p[0] = p[2]
def p_expression_literal(p):
    """expression : STRING
                  | FLOAT
                  | INT"""
    p[0] = AST_Literal(p[1])

def p_expression_true(p):
    "expression : TRUE"
    p[0] = AST_Literal(True)

def p_expression_false(p):
    "expression : FALSE"
    p[0] = AST_Literal(False)

def p_expression_sum(p):
    "expression : expression '+' expression"
    p[0] = AST_Sum(p[1], p[3])

def p_expression_sub(p):
    "expression : expression '-' expression"
    p[0] = AST_Sub(p[1], p[3])

def p_expression_mult(p):
    "expression : expression '*' expression"
    p[0] = AST_Mult(p[1], p[3])

def p_expression_div(p):
    "expression : expression '/' expression"
    p[0] = AST_Div(p[1], p[3])

def p_expression_idiv(p):
    "expression : expression IDIV expression"
    p[0] = AST_IDiv(p[1], p[3])

def p_expression_modulo(p):
    "expression : expression '%' expression"
    p[0] = AST_Mod(p[1], p[3])

def p_expression_equals(p):
    "expression : expression EQUALS expression"
    p[0] = AST_Equals(p[1], p[3])

def p_expression_nequals(p):
    "expression : expression NEQUALS expression"
    p[0] = AST_NEquals(p[1], p[3])

def p_expression_gt(p):
    "expression : expression '>' expression"
    p[0] = AST_GT(p[1], p[3])

def p_expression_gte(p):
    "expression : expression GTE expression"
    p[0] = AST_GTE(p[1], p[3])

def p_expression_lt(p):
    "expression : expression '<' expression"
    p[0] = AST_LT(p[1], p[3])

def p_expression_lte(p):
    "expression : expression LTE expression"
    p[0] = AST_LTE(p[1], p[3])

def p_expression_and(p):
    "expression : expression AND expression"
    p[0] = AST_And(p[1], p[3])

def p_expression_or(p):
    "expression : expression OR expression"
    p[0] = AST_Or(p[1], p[3])

def p_expression_not(p):
    "expression : NOT expression"
    p[0] = AST_Not(p[2])

def p_expression_cond(p):
    "expression : COND '(' expression ',' expression ',' expression ')'"
    p[0] = AST_Cond(p[3], p[5], p[7])

def p_expression_funname(p):
    "expression : FUNCNAME"
    p[0] = AST_Funcname(p[1])

def p_expression_name(p):
    "expression : LOOKUP"
    p[0] = AST_Lookup(p[1])

def p_expression_variable(p):
    "expression : ARGNAME"
    p[0] = AST_Argname(p[1])

def p_expression_auto(p):
    "expression : AUTO"
    p[0] = AST_Auto()  # TODO

def p_expression_autoquery(p):
    "expression : AUTOQUERY"
    assert False  # TODO

# p_argument turns an expression exp into a function argument, e.g. for use in f(exp)
# To be consistent with Python, function arguments can be of the form
# exp, *exp, **exp, $name=exp
# We do not wrap exp (and possibly name) into one of 4 different AST_FOO - types.
# The reason is that eval_ast could not do anything meaningful:
# If exp = [1, 2], then the corresponding AST_STARRED_EXP(exp).eval_ast
# should NOT naturally return the tuple 1, 2, since then for a function g(a,b) with
# arguments, g(*exp) would bind a to the tuple (1,2) and leave b unbound...
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

def p_argument_exp(p):
    "argument : expression"
    p[0] = p[1]
    p[0].argtype = _FUNARG_EXP

def p_argument_listexp(p):
    "argument : '*' expression"
    p[0] = p[2]
    p[0].argtype = _FUNARG_STAREXP
    p[0].typedesc = '*' + p[0].typedesc  # this creates an instance variable
    
def p_argument_dictexp(p):
    "argument : '*' '*' expression"
    p[0] = p[3]
    p[0].argtype = _FUNARG_STARSTAREXP
    p[0].typedesc = '**' + p[0].typedesc  # this creates an instance variable

def p_argument_nameval(p):
    "argument : ARGNAME '=' expression"
    p[0] = p[3]
    p[0].argtype = _FUNARG_NAMEVAL
    p[0].namebind = p[1]
    p[0].typedesc = p[0].typedesc + ' bound to ' + p[0].namebind  # += actually would work (which I find strange)

def p_arglist(p):
    """arglist :
               | arglist_nonempty"""
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

def p_function_call(p):
    "expression : expression '(' arglist ')'"
    # keyword arguments must come after positional arguments :
    kwonly = False
    for arg in p[3]:
        if arg.argtype is _FUNARG_STARSTAREXP or arg.argtype is _FUNARG_NAMEVAL:
            kwonly = True
        elif kwonly:
            lexer.needs_env = set()
            raise CGParseException("Positional arguments must not follow keyword arguments")
    p[0] = AST_FunctionCall(p[1], *p[3])
    



def p_getitem(p):
    "expression : expression '[' expression ']'"
    p[0] = AST_GetItem(p[1], p[3])

_ARGTYPE_NORMAL = 'Arg'  # def f(x)
_ARGTYPE_DEFAULT = 'Defaulted Argument'  # def f(x=5)
_ARGTYPE_STAR = 'End of Positional Arguments'  # def f(*)
_ARGTYPE_STARARG = 'Rest of Positional Arguments'  # def f(*arg)
_ARGTYPE_KWARGS = 'Rest of Keyword Arguments'  # def (f**kwargs)

def p_declarg_name(p):
    "declarg : ARGNAME"
    p[0] = (p[1], _ARGTYPE_NORMAL)

def p_declarg_defaulted_name(p):
    "declarg : ARGNAME '=' expression"
    p[0] = (p[1], _ARGTYPE_DEFAULT, p[3])

def p_declarg_pos_end(p):
    "declarg : '*'"
    p[0] = (None, _ARGTYPE_STAR)

def p_declarg_pos_rest(p):
    "declarg : '*' ARGNAME"
    p[0] = (p[2], _ARGTYPE_STARARG)

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

def p_declarglist_nonempty(p):
    """declarglist_nonempty : declarg
                            | declarglist_nonempty ',' declarg"""
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = p[1] + [p[3]]

def p_functiondef(p):
    "expression : FUN '[' declarglist ']' '(' expression ')'"
    args = p[3]
    # Check validity of argument list : There are restrictions on the order of argument types (kw-arguments after positional arguments etc)
    seen_default = False
    seen_restkw = False
    seen_end = False
    for arg in args:
        if seen_end:
            lexer.needs_env = set()
            raise CGParseException("Arguments after end of kwargs")
        if arg[1] is _ARGTYPE_NORMAL:  # normal argument $a
            if seen_default and not seen_restkw:
                lexer.needs_env = set()
                raise CGParseException("positional arg after defaulted arg")
        elif arg[1] is _ARGTYPE_DEFAULT:  # defaulted argument $a = 1
            seen_default = True
        elif (arg[1] is _ARGTYPE_STAR) or (arg[1] is _ARGTYPE_STARARG):  # end of positional arguments * or *$a
            if seen_restkw:
                lexer.needs_env = set()
                raise CGParseException("taking rest of positional arguments multiple times")
            seen_restkw = True
        elif arg[1] is _ARGTYPE_KWARGS:  # **$kwargs must be last
            seen_end = True
        else:
            assert False
    p[0] = AST_Lambda(args, p[6])  # Note that p[3] is a list

parser = yacc.yacc()

# for debugging.
# if __name__ == '__main__':
#     lex.runmain()
