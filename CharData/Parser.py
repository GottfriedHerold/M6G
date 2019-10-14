import ply.lex as lex
import ply.yacc as yacc
from ply.lex import TOKEN
# list of tokens (excluding literals):
from .Regexps import re_key_any
from .CharExceptions import DataError

keywords = [
    'COND',
    'OR',
    'AND',
    'NOT',
    'FUN',  # alternative: LAMBDA is also recognized
]

# $Name tokens, where Name starts with a capital letter will be recognized iff(!) Name.upper() is in this dict.
# Right-Hand sides need to be in tokens
special_args = {
    'A': 'AUTO',  # $AUTO evaluates to whatever it would, if the AST was empty
    'AUTO': 'AUTO',
    'Q': 'QUERY',  # $QUERY is the query string, usually equals to $NAME. Its presence needs special treatment.
    'QUERY': 'QUERY',
    'NAME': 'ARGNAME',  # This acts as a normal argument!
}

tokens = [
    'STRING',
    'IDIV',
    'INT',
    'FLOAT',
    'FUNCNAME',
    'NAME',
    'EQUALS',
    'NEQUALS',
    'LTE',
    'GTE',
    'ARGNAME',
    'AUTO',
    'QUERY',
] + keywords
literals = "+-*/%()[],<>="

# Note: Order matters!
# Function defs come first (in order of definition), then t_TOKEN = regexp defs (in order of decreasing length of regexp)
# then literals

def t_STRING(token):
    r"(?:'[^']*')|" r'(?:"[^"]*")'  # Allow either ' or " as delimeters (Python-like)
    token.value = token.value[1:-1]  #strip the quotation marks already by the lexer
    return token

def t_FLOAT(token):
    r"[0-9]+[.][0-9]+"
    token.value = float(token.value)
    return token

# This must come after t_FLOAT
def t_INT(token):
    r"[0-9]+"
    token.value = int(token.value)
    return token

def t_ARGNAME(token):
    r"[$][a-z_]+"
    token.value = token.value[1:]
    return token

def t_SPECIALARGS(token):
    r"[$][A-Z][a-zA-Z_]*"
    token.value = token.value[1:].upper()
    if token.value in special_args:
        token.type = special_args[token.value]
        token.value = token.type
        return token
    else:
        raise SyntaxError("Invalid argument name $" + token.value)

# keywords and the like
def t_FUNCNAME(token):
    r"[A-Z]+"  # No underscores for now
    if token.value in keywords:
        token.type = token.value
    if token.value == 'LAMBDA':
        token.type = 'FUN'
    return token

def t_BLAH(token):
    r"[#]"
    token.type = 'INT'
    return token

# reference to other data field
@TOKEN(re_key_any.pattern)
def t_NAME(token):
    return token

t_ignore = ' \t\n\r\f\v'  # ignore (ASCII) whitespace

t_IDIV = r"//"
t_EQUALS = r"=="
t_NEQUALS = r"!="
t_LTE = r"<="
t_GTE = r">="

lexer = lex.lex()

class AST:
    typedesc = 'Parent'
    def __init__(self, *kw):
        self.child = kw
    def __str__(self):
        return self.typedesc + '[' + ", ".join([str(x) for x in self.child]) + ']'

class AST_BinOp(AST):
    typedesc = 'Binary Op'
    def eval_ast(self, list, context):
        left = self.child[0].eval_ast(list, context)
        if isinstance(left, DataError):
            return left
        right = self.child[1].eval_ast(list, context)
        if isinstance(right, DataError):
            return right
        return self.eval_fun(left, right)

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

class AST_And(AST):  # Not BinOp!
    typedesc = 'AND'
    def eval_ast(self, list, context):
        left = self.child[0].eval_ast(list, context)
        if (not left) or isinstance(left, DataError):
            return left
        return self.child[1].eval_ast(list, context)

class AST_Or(AST):  # Not BinOp!
    typedesc = 'OR'
    def eval_ast(self, list, context):
        left = self.child[0].eval_ast(list, context)
        if left:
            return left
        return self.child[1].eval_ast(list, context)

class AST_Cond(AST):
    typedesc = 'COND'
    def eval_ast(self, list, context):
        cond = self.child[0].eval_ast(list, context)
        if isinstance(cond, DataError):
            return cond
        if cond:
            return self.child[1].eval_ast(list, context)
        else:
            return self.child[2].eval_ast(list, context)

class AST_Literal(AST):
    typedesc = 'Literal'
    def eval_ast(self, list, context):
        return self.child[0]

class AST_Name(AST):
    typedesc = 'Reference'
    def eval_ast(self, list, context):
        assert False

class AST_Funcname(AST):
    typedesc = 'Function Name'
    def eval_ast(self, list, context):
        if self.child[0] == 'LIST':
            return lambda *kw: [*kw]
        if self.child[0] == 'DICT':
            return dict
        if self.child[0] == 'SORTED':
            return sorted
        assert False


class AST_Argname(AST):
    typedesc = 'Argument'
    def eval_ast(self, list, context):
        return context[self.child[0]]

class AST_Auto(AST):
    typedesc = 'Auto'
    def eval_ast(self, list, context):
        assert False

class AST_FunctionCall(AST):
    typedesc = 'Call'
    def eval_ast(self, list, context):
        fun = self.child[0].eval_ast(list, context)
        if isinstance(fun, DataError):
            return fun
        posargs = []
        kwargs = {}
        for arg in self.child[1:]:
            a = arg.eval_ast(list, context)
            if isinstance(a, DataError):
                return a
            if arg.argtype == 0:
                posargs.append(a)
            elif arg.argtype == 1:
                posargs.append(*a)
            elif arg.argtype == 2:
                kwargs.update(**a)
            else:
                assert arg.argtype == 3
                kwargs[arg.namebind] = a
        return fun(*posargs, **kwargs)

class AST_Lambda(AST):
    typedesc = 'Lambda'
    def eval_ast(self, list, context):
        # self.child[0] is a list of pairs (name, type) or triples (name, type, defaultarg) for the variable names:
        # name is a string denoting the actual name (or None for *)
        # type is a string in {'Arg', 'DefArg', 'EndPosArg', 'RestPosArg', 'RestKwArg'} to differentiate
        # name, name = default, *, *name and **name
        # self.child[1] is an AST for the actual function body.
        # As opposed to Python proper, it does not matter when we evaluate default arguments...

        # Captures: list and context
        givenargs = self.child[0]
        body = self.child[1]

        def fun(*funargs, **kwargs):
            new_context = {}
            funargpos = 0
            funarglen = len(funargs)
            kwarg_used = False

            for arg in givenargs:
                if arg[1] == 'Arg' or arg[1] == 'DefArg':
                    if arg[0] in kwargs:
                        new_context[arg[0]] = kwargs.pop[arg[0]]
                        kwarg_used = True
                    elif funargpos < funarglen:  # Still have arguments given to fun left

                        new_context[arg[0]] = funargs[funargpos]
                        funargpos+=1



            pass

        return fun

class AST_GetItem(AST_BinOp):
    typedesc = 'GetItem'
    @staticmethod
    def eval_fun(container, index):
        return container[index]

start = 'expression'
precedence = (
    ('right', 'OR'),
    ('right', 'AND'),
    ('right', 'NOT'),
    ('nonassoc', 'LTE', 'GTE', '<', '>', 'EQUALS', 'NEQUALS'),
    ('left', '+', '-'),
    ('left', '*', '/', '%', 'IDIV')
)


def p_expression_bracket(p):
    "expression : '(' expression ')' "
    p[0] = p[2]
def p_expression_literal(p):
    """expression : STRING
                  | FLOAT
                  | INT"""
    p[0] = AST_Literal(p[1])

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

def p_expression_cond(p):
    "expression : COND '(' expression ',' expression ',' expression ')'"
    p[0] = AST_Cond(p[3], p[5], p[7])

def p_expression_funname(p):
    "expression : FUNCNAME"
    p[0] = AST_Funcname(p[1])

def p_expression_name(p):
    "expression : NAME"
    p[0] = AST_Name(p[1])

def p_expression_variable(p):
    "expression : ARGNAME"
    p[0] = AST_Argname(p[1])

def p_expression_auto(p):
    "expression : AUTO"
    p[0] = AST_Auto()

# p_argument turns an expression exp into a function argument, e.g. for use in f(exp)
# To be consistent with Python, function arguments can be of the form
# exp, *exp, **exp, $name=exp
# We do not wrap exp (and possibly name) into one of 4 different AST_FOO - types.
# The reason is that eval_ast could not do anything meaningful:
# If exp = [1, 2], then the corresponding AST_STARRED_EXP(exp).eval_ast
# should NOT naturally return the tuple 1, 2, since then for a function g(a,b) with
# arguments, g(*exp) would bind a to the tuple (1,2) and leave b unbound...
# In fact, *exp is not a valid Python expression in most contexts.
# The unpacking and the function call have to be handled simultaneously and we just mark the arguments
# the p[0].typedesc = ... assignment is just for debugging and printing.
# Note that p[0].typedesc on the left-hand side is an instance variable, the right-hand side a class variable!
# p[0].typedesc += "..." would actually work and create an instance variable
def p_argument_exp(p):
    "argument : expression"
    p[0] = p[1]
    p[0].argtype = 0

def p_argument_listexp(p):
    "argument : '*' expression"
    p[0] = p[2]
    p[0].argtype = 1
    p[0].typedesc = '*' + p[0].typedesc  # this creates an instance variable

def p_argument_dictexp(p):
    "argument : '*' '*' expression"
    p[0] = p[3]
    p[0].argtype = 2
    p[0].typedesc = '**' + p[0].typedesc  # this creates an instance variable

def p_argument_nameval(p):
    "argument : ARGNAME '=' expression"
    p[0] = p[3]
    p[0].argtype = 3
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
    p[0] = AST_FunctionCall(p[1], *p[3])
    kwonly = False
    for arg in p[3]:
        if arg.argtype == 2 or arg.argtype == 3:
            kwonly = True
        elif kwonly:
            raise SyntaxError("Positional arguments must not follow keyword arguments")



def p_getitem(p):
    "expression : expression '[' expression ']'"
    p[0] = AST_GetItem(p[1], p[3])

def p_declarg_name(p):
    "declarg : ARGNAME"
    p[0] = (p[1], 'Arg')

def p_declarg_defaulted_name(p):
    "declarg : ARGNAME '=' expression"
    p[0] = (p[1], 'DefArg', p[3])

def p_declarg_pos_end(p):
    "declarg : '*'"
    p[0] = (None, 'EndPosArg')

def p_declarg_pos_rest(p):
    "declarg : '*' ARGNAME"
    p[0] = (p[2], 'RestPosArg')

def p_declarg_kw_rest(p):
    "declarg : '*' '*' ARGNAME"
    p[0] = (p[3], 'RestKwArg')

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
    seen_default = False
    seen_restkw = False
    seen_end = False
    for arg in args:
        if seen_end:
            raise SyntaxError("Arguments after end of kwargs")
        if arg[1] == 'Arg':  # normal argument $a
            if seen_default and not seen_restkw:
                raise SyntaxError("positional arg after defaulted arg")
        elif arg[1] == 'DefArg':  # defaulted argument $a = 1
            seen_default = True
        elif arg[1] == 'EndPosArg' or arg[1] == 'RestPosArg': # end of positional arguments * or *$a
            if seen_restkw:
                raise SyntaxError("taking rest of positional arguments multiple times")
            seen_restkw = True
        elif arg[1] == 'RestKwArg':  # **$kwargs must be last
            seen_end = True
        else:
            assert False
    p[0] = AST_Lambda(args, p[6])  # Note that p[3] is a list

parser = yacc.yacc()

# for debugging.
if __name__ == '__main__':
    lex.runmain()