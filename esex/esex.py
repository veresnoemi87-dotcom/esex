#!/usr/bin/env python3
"""
ESEX 5.5 - native Windows x64 compiler for the ES (Executable Script) language.

    esex game.es              ->  game.exe
    esex game.es -o out.exe
    esex game.es --check      ->  syntax/semantic check only, writes nothing
    esex game.es --run        ->  compile, then start it (Windows)
    esex -v                   ->  print the version

No C compiler, linker or runtime is needed: ESEX writes the machine code and the
PE file itself.  See README.md for the language reference.
"""
import sys
import os
import struct
import difflib

VERSION = "5.5.0"
IMAGE_BASE = 0x140000000


class ESError(Exception):
    def __init__(self, msg, line=None):
        self.msg = msg
        self.line = line
        super().__init__(("line %d: %s" % (line, msg)) if line else msg)


# ----------------------------------------------------------------------------
# Colours
# ----------------------------------------------------------------------------
NAMED_COLORS = {
    'black': (0, 0, 0), 'white': (255, 255, 255), 'red': (255, 0, 0),
    'green': (0, 255, 0), 'blue': (0, 0, 255), 'yellow': (255, 255, 0),
    'cyan': (0, 255, 255), 'magenta': (255, 0, 255), 'orange': (255, 165, 0),
    'purple': (128, 0, 128), 'pink': (255, 105, 180), 'brown': (139, 69, 19),
    'gray': (128, 128, 128), 'grey': (128, 128, 128), 'gold': (255, 204, 51),
    'lime': (50, 205, 50), 'navy': (0, 0, 128), 'teal': (0, 128, 128),
    'silver': (192, 192, 192), 'darkgray': (64, 64, 64), 'lightgray': (211, 211, 211),
}


def colorref(r, g, b):
    return (b << 16) | (g << 8) | r


def parse_color(s, line=None):
    s = str(s).strip()
    if s.startswith('#'):
        h = s[1:]
        if len(h) == 3:
            h = ''.join(c * 2 for c in h)
        try:
            if len(h) in (6, 8):
                return colorref(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        except ValueError:
            pass
        raise ESError("bad colour '%s'" % s, line)
    if s.lower() in NAMED_COLORS:
        return colorref(*NAMED_COLORS[s.lower()])
    raise ESError("unknown colour '%s'" % s, line)


def shade(ref, delta):
    r, g, b = ref & 255, (ref >> 8) & 255, (ref >> 16) & 255
    c = lambda v: max(0, min(255, v + delta))
    return colorref(c(r), c(g), c(b))


# ----------------------------------------------------------------------------
# Lexer
# ----------------------------------------------------------------------------
class Tok:
    __slots__ = ('kind', 'val', 'line')

    def __init__(self, kind, val, line):
        self.kind, self.val, self.line = kind, val, line

    def __repr__(self):
        return "Tok(%s,%r)" % (self.kind, self.val)


TWO_CHAR_OPS = ('==', '!=', '<=', '>=', '&&', '||', '+=', '-=', '*=', '/=', '%=',
                '++', '--', '..')
ONE_CHAR_OPS = '+-*/%<>=!(){},:?'
WORD_OPS = {'and': '&&', 'or': '||', 'not': '!'}
LBRACE, RBRACE = '\x01', '\x02'      # escaped { and } inside strings


def tokenize(src, line0=1):
    toks, stack = [], []
    i, n, line = 0, len(src), line0

    def add(kind, val):
        toks.append(Tok(kind, val, line))

    while i < n:
        c = src[i]
        if c == '\n':
            if not stack or stack[-1] != 'p':
                add('nl', '\n')
            line += 1
            i += 1
            continue
        if c in ' \t\r\xa0\ufeff':
            i += 1
            continue
        if c == ';':
            add('nl', ';')
            i += 1
            continue
        if src.startswith('//', i):
            while i < n and src[i] != '\n':
                i += 1
            continue
        if src.startswith('/*', i):
            j = src.find('*/', i + 2)
            if j < 0:
                raise ESError("unterminated /* comment", line)
            line += src.count('\n', i, j)
            i = j + 2
            continue
        if c in '"\'':
            q, j, buf = c, i + 1, []
            while True:
                if j >= n or src[j] == '\n':
                    raise ESError("unterminated string", line)
                ch = src[j]
                if ch == q:
                    break
                if ch == '\\' and j + 1 < n:
                    e = src[j + 1]
                    buf.append({'n': '\n', 't': '\t', '\\': '\\', '"': '"', "'": "'",
                                '{': LBRACE, '}': RBRACE}.get(e, '\\' + e))
                    j += 2
                    continue
                buf.append(ch)
                j += 1
            add('str', ''.join(buf))
            i = j + 1
            continue
        if c == '#':
            j = i + 1
            while j < n and src[j] in '0123456789abcdefABCDEF':
                j += 1
            add('str', src[i:j])
            i = j
            continue
        if c.isdigit():
            j = i
            if src.startswith(('0x', '0X'), i):
                j = i + 2
                while j < n and src[j] in '0123456789abcdefABCDEF':
                    j += 1
                add('num', int(src[i:j], 16))
            else:
                while j < n and src[j].isdigit():
                    j += 1
                add('num', int(src[i:j]))
            i = j
            continue
        if c.isalpha() or c == '_':
            j = i
            while j < n and (src[j].isalnum() or src[j] == '_'):
                j += 1
            while j + 1 < n and src[j] == '.' and (src[j + 1].isalpha() or src[j + 1] == '_'):
                j += 1
                while j < n and (src[j].isalnum() or src[j] == '_'):
                    j += 1
            word = src[i:j]
            if word in WORD_OPS:
                add('op', WORD_OPS[word])
            else:
                add('id', word)
            i = j
            continue
        two = src[i:i + 2]
        if two in TWO_CHAR_OPS:
            add('op', two)
            i += 2
            continue
        if c in ONE_CHAR_OPS:
            if c == '(':
                stack.append('p')
            elif c == '{':
                stack.append('b')
            elif c in ')}' and stack:
                stack.pop()
            add('op', c)
            i += 1
            continue
        raise ESError("unexpected character %r" % c, line)
    add('nl', '\n')
    add('eof', None)
    return toks


# ----------------------------------------------------------------------------
# Parser  (AST = plain tuples)
#   stmt: ('assign', name, expr, line) ('if', cond, then, else, line)
#         ('while', cond, body, line)  ('call', name, args, line)
#   expr: ('num', v) ('str', s) ('var', name) ('bin', op, a, b) ('un', op, a)
#         ('call', name, args, line) ('tern', cond, a, b) ('block', stmts)
#   args: [(keyword-or-None, expr), ...]
# ----------------------------------------------------------------------------
class Parser:
    def __init__(self, toks):
        self.t, self.p = toks, 0
        self.hidden = 0

    def hidden_name(self, what):
        self.hidden += 1
        return '__%s%d' % (what, self.hidden)

    def peek(self, k=0):
        return self.t[min(self.p + k, len(self.t) - 1)]

    def next(self):
        tok = self.t[self.p]
        if tok.kind != 'eof':
            self.p += 1
        return tok

    def is_op(self, v, k=0):
        t = self.peek(k)
        return t.kind == 'op' and t.val == v

    def expect_op(self, v):
        t = self.next()
        if not (t.kind == 'op' and t.val == v):
            raise ESError("expected '%s' but found %s" % (v, self.describe(t)), t.line)
        return t

    @staticmethod
    def describe(t):
        return "end of file" if t.kind == 'eof' else ("newline" if t.kind == 'nl' else repr(t.val))

    def skip_nl(self):
        while self.peek().kind == 'nl':
            self.p += 1

    def parse_program(self):
        stmts = []
        self.skip_nl()
        while self.peek().kind != 'eof':
            stmts.append(self.parse_stmt())
            self.end_stmt()
            self.skip_nl()
        return stmts

    def end_stmt(self):
        t = self.peek()
        if t.kind in ('nl', 'eof') or (t.kind == 'op' and t.val == '}'):
            return
        raise ESError("unexpected %s" % self.describe(t), t.line)

    def parse_block(self):
        self.expect_op('{')
        stmts = []
        self.skip_nl()
        while not self.is_op('}'):
            if self.peek().kind == 'eof':
                raise ESError("missing '}'", self.peek().line)
            stmts.append(self.parse_stmt())
            self.end_stmt()
            self.skip_nl()
        self.expect_op('}')
        return stmts

    def parse_stmt(self):
        t = self.peek()
        line = t.line
        if t.kind != 'id':
            raise ESError("unexpected %s" % self.describe(t), line)
        v = t.val
        if v in ('let', 'var', 'const'):
            self.next()
            nm = self.next()
            if nm.kind != 'id':
                raise ESError("expected a variable name after '%s'" % v, line)
            self.expect_op('=')
            return ('assign', self.check_name(nm), self.parse_expr(), line)
        if v == 'if':
            self.next()
            cond = self.parse_expr()
            then = self.parse_block()
            save = self.p
            self.skip_nl()
            els = []
            if self.peek().kind == 'id' and self.peek().val == 'else':
                self.next()
                self.skip_nl()
                if self.peek().kind == 'id' and self.peek().val == 'if':
                    els = [self.parse_stmt()]
                else:
                    els = self.parse_block()
            else:
                self.p = save
            return ('if', cond, then, els, line)
        if v == 'while':
            self.next()
            cond = self.parse_expr()
            return ('while', cond, self.parse_block(), line, [], [])
        if v == 'loop':
            self.next()
            return ('while', ('num', 1), self.parse_block(), line, [], [])
        if v in ('break', 'continue'):
            self.next()
            return (v, line)
        if v == 'repeat':
            self.next()
            count = self.parse_expr()
            body = self.parse_block()
            i, n = self.hidden_name('r'), self.hidden_name('n')
            return ('while', ('bin', '<', ('var', i), ('var', n)), body, line,
                    [('assign', i, ('bin', '+', ('var', i), ('num', 1)), line)],
                    [('assign', i, ('num', 0), line), ('assign', n, count, line)])
        if v == 'for':
            return self.parse_for(line)
        if v == 'fn':
            return self.parse_fn(line)
        nxt = self.peek(1)
        if nxt.kind == 'op' and nxt.val in ('++', '--'):
            self.next()
            self.next()
            return ('assign', self.check_name(t),
                    ('bin', nxt.val[0], ('var', v), ('num', 1)), line)
        if nxt.kind == 'op' and nxt.val in ('=', '+=', '-=', '*=', '/=', '%='):
            self.next()
            self.next()
            e = self.parse_expr()
            if nxt.val != '=':
                e = ('bin', nxt.val[0], ('var', v), e)
            return ('assign', self.check_name(t), e, line)
        if nxt.kind == 'op' and nxt.val == '(':
            self.next()
            return ('call', v, self.parse_args(), line)
        self.next()
        return ('call', v, [], line)

    def parse_for(self, line):
        """for i in 0..10 { }   for i in 0..=10 { }   for i in 0..100 step 5 { }"""
        self.next()
        nm = self.next()
        if nm.kind != 'id' or '.' in nm.val:
            raise ESError("expected a loop variable name after 'for'", line)
        kw = self.next()
        if not (kw.kind == 'id' and kw.val == 'in'):
            raise ESError("expected 'in' after 'for %s'" % nm.val, line)
        start = self.parse_expr()
        self.expect_op('..')
        inclusive = False
        if self.is_op('='):
            self.next()
            inclusive = True
        stop = self.parse_expr()
        step = ('num', 1)
        if self.peek().kind == 'id' and self.peek().val == 'step':
            self.next()
            step = self.parse_expr()
        body = self.parse_block()
        limit = self.hidden_name('l')
        down = step[0] == 'num' and step[1] < 0
        op = ('>=' if inclusive else '>') if down else ('<=' if inclusive else '<')
        return ('while', ('bin', op, ('var', nm.val), ('var', limit)), body, line,
                [('assign', nm.val, ('bin', '+', ('var', nm.val), step), line)],
                [('assign', nm.val, start, line), ('assign', limit, stop, line)])

    def parse_fn(self, line):
        """fn name(a, b) { ... }  -- a user command, inlined at every call."""
        self.next()
        nm = self.next()
        if nm.kind != 'id' or '.' in nm.val:
            raise ESError("expected a function name after 'fn'", line)
        self.expect_op('(')
        params = []
        while True:
            self.skip_nl()
            if self.is_op(')'):
                break
            t = self.next()
            if t.kind != 'id' or '.' in t.val:
                raise ESError("expected a parameter name but found %s" % self.describe(t), t.line)
            params.append(t.val)
            self.skip_nl()
            if self.is_op(','):
                self.next()
                continue
            if not self.is_op(')'):
                t = self.peek()
                raise ESError("expected ',' or ')' but found %s" % self.describe(t), t.line)
        self.expect_op(')')
        return ('fn', nm.val, params, self.parse_block(), line)

    @staticmethod
    def check_name(tok):
        if '.' in tok.val:
            raise ESError("cannot assign to '%s'" % tok.val, tok.line)
        return tok.val

    def parse_args(self):
        self.expect_op('(')
        args = []
        while True:
            self.skip_nl()
            if self.is_op(')'):
                break
            name = None
            t = self.peek()
            if t.kind == 'id' and self.is_op(':', 1):
                name = t.val
                self.p += 2
                self.skip_nl()
            if self.is_op('{'):
                val = ('block', self.parse_block())
            else:
                val = self.parse_expr()
            args.append((name, val))
            self.skip_nl()
            if self.is_op(','):
                self.next()
                continue
            if not self.is_op(')'):
                t = self.peek()
                raise ESError("expected ',' or ')' but found %s" % self.describe(t), t.line)
        self.expect_op(')')
        return args

    # expressions ----------------------------------------------------------
    def parse_expr(self):
        cond = self.parse_bin(0)
        if self.is_op('?'):
            self.next()
            a = self.parse_expr()
            self.expect_op(':')
            return ('tern', cond, a, self.parse_expr())
        return cond

    LEVELS = [('||',), ('&&',), ('==', '!='), ('<', '<=', '>', '>='), ('+', '-'), ('*', '/', '%')]

    def parse_bin(self, lvl):
        if lvl == len(self.LEVELS):
            return self.parse_unary()
        left = self.parse_bin(lvl + 1)
        while self.peek().kind == 'op' and self.peek().val in self.LEVELS[lvl]:
            op = self.next().val
            left = ('bin', op, left, self.parse_bin(lvl + 1))
        return left

    def parse_unary(self):
        if self.is_op('-'):
            self.next()
            e = self.parse_unary()
            return ('num', -e[1]) if e[0] == 'num' else ('un', '-', e)
        if self.is_op('!'):
            self.next()
            return ('un', '!', self.parse_unary())
        return self.parse_primary()

    def parse_primary(self):
        t = self.next()
        if t.kind == 'num':
            return ('num', t.val)
        if t.kind == 'str':
            return ('str', t.val)
        if t.kind == 'op' and t.val == '(':
            e = self.parse_expr()
            self.expect_op(')')
            return e
        if t.kind == 'id':
            if t.val == 'true':
                return ('num', 1)
            if t.val == 'false':
                return ('num', 0)
            if self.is_op('('):
                return ('call', t.val, self.parse_args(), t.line)
            if t.val in ('time.s', 'time.sec'):
                return ('bin', '/', ('var', 'time.ms'), ('num', 1000))
            return ('var', t.val)
        raise ESError("unexpected %s in expression" % self.describe(t), t.line)


def parse_source(src, line0=1):
    return Parser(tokenize(src, line0)).parse_program()


def parse_interp(s, line=None):
    """Split "Score: {score}" into [('lit','Score: '), ('expr', node)]."""
    segs, buf, i = [], [], 0
    while i < len(s):
        c = s[i]
        if c == '{':
            j = s.find('}', i)
            if j < 0:
                raise ESError("missing '}' in string", line)
            if buf:
                segs.append(('lit', ''.join(buf)))
                buf = []
            toks = tokenize(s[i + 1:j], line or 1)
            p = Parser(toks)
            node = p.parse_expr()
            if p.peek().kind not in ('nl', 'eof'):
                raise ESError("bad expression inside { } in string", line)
            segs.append(('expr', node))
            i = j + 1
            continue
        buf.append(c)
        i += 1
    if buf:
        segs.append(('lit', ''.join(buf)))
    return [(k, v.replace(LBRACE, '{').replace(RBRACE, '}') if k == 'lit' else v) for k, v in segs]


# ----------------------------------------------------------------------------
# Language tables
# ----------------------------------------------------------------------------
BUILTIN_VARS = {'mouse.x', 'mouse.y', 'mouse_x', 'mouse_y', 'mouse.down', 'mouse.right',
                'mouse.clicked',
                'window.w', 'window.h', 'window.width', 'window.height', 'frame', 'time.ms'}
DRAW_CALLS = {'draw.text', 'draw.rect', 'draw.roundrect', 'draw.circle', 'draw.line',
              'draw.ellipse', 'draw.clear', 'draw.bar'}
UI_CALLS = {'button', 'area'}
CONFIG_CALLS = {'window', 'resizable.enable', 'resizable.disable'}
ACTION_CALLS = {'exit', 'beep', 'alert', 'title'}
CALL_ALIASES = {'add.text': 'draw.text', 'draw.rectangle': 'draw.rect', 'new.window': 'window',
                'sound.beep': 'beep', 'draw.rrect': 'draw.roundrect'}
PARAMS = {
    'draw.text': ['x', 'y', 'text', 'color', 'size', 'bold', 'align'],
    'draw.rect': ['x', 'y', 'w', 'h', 'color', 'outline'],
    'draw.roundrect': ['x', 'y', 'w', 'h', 'color', 'radius', 'outline'],
    'draw.circle': ['x', 'y', 'r', 'color', 'outline'],
    'draw.line': ['x1', 'y1', 'x2', 'y2', 'color', 'width'],
    'draw.ellipse': ['x', 'y', 'w', 'h', 'color', 'outline'],
    'draw.clear': ['color'],
    'draw.bar': ['x', 'y', 'w', 'h', 'value', 'max', 'color', 'back'],
    'button': ['x', 'y', 'w', 'h', 'text', 'onclick', 'color', 'size'],
    'area': ['x', 'y', 'w', 'h', 'onclick'],
}
PARAM_ALIASES = {'width': 'w', 'height': 'h', 'radius': 'r', 'colour': 'color'}
EXPR_FUNCS = {'key.down', 'key.pressed', 'math.random', 'random', 'abs', 'min', 'max',
              'clamp', 'sqrt', 'rgb', 'sign', 'sq', 'dist', 'mouse.over'}

KEY_NAMES = {'SPACE': 0x20, 'ENTER': 0x0D, 'RETURN': 0x0D, 'ESC': 0x1B, 'ESCAPE': 0x1B,
             'LEFT': 0x25, 'UP': 0x26, 'RIGHT': 0x27, 'DOWN': 0x28, 'SHIFT': 0x10,
             'CTRL': 0x11, 'ALT': 0x12, 'TAB': 0x09, 'BACKSPACE': 0x08, 'DELETE': 0x2E,
             'MOUSE': 0x01, 'LMOUSE': 0x01, 'RMOUSE': 0x02, 'HOME': 0x24, 'END': 0x23,
             'PAGEUP': 0x21, 'PAGEDOWN': 0x22, 'INSERT': 0x2D, 'MINUS': 0xBD, 'PLUS': 0xBB,
             'COMMA': 0xBC, 'PERIOD': 0xBE, 'WIN': 0x5B}


def key_code(node, line=None):
    if node[0] == 'str':
        name = node[1]
    elif node[0] == 'var':
        name = node[1]
    else:
        raise ESError("key name expected, e.g. key.down(\"SPACE\")", line)
    up = name.upper()
    if up in KEY_NAMES:
        return KEY_NAMES[up]
    if len(up) == 1 and (up.isalpha() or up.isdigit()) and up.isascii():
        return ord(up)
    if up[0] == 'F' and up[1:].isdigit() and 1 <= int(up[1:]) <= 12:
        return 0x70 + int(up[1:]) - 1
    if up.startswith('NUM') and up[3:].isdigit() and len(up) == 4:
        return 0x60 + int(up[3:])
    raise ESError("unknown key '%s'" % name, line)



def bind_args(name, args, line):
    params = PARAMS[name]
    out, pos = {}, 0
    for k, v in args:
        if k is None:
            if pos >= len(params):
                raise ESError("too many arguments for %s" % name, line)
            k = params[pos]
            pos += 1
        elif k not in params:
            k = PARAM_ALIASES.get(k, k)
            if k not in params:
                raise ESError("%s has no option '%s'" % (name, k), line)
        out[k] = v
    return out


def unescape(s):
    return s.replace(LBRACE, '{').replace(RBRACE, '}')


def const_eval(node, what):
    t = node[0]
    if t == 'num':
        return node[1]
    if t == 'un' and node[1] == '-':
        return -const_eval(node[2], what)
    if t == 'bin' and node[1] in '+-*/':
        a, b = const_eval(node[2], what), const_eval(node[3], what)
        return {'+': a + b, '-': a - b, '*': a * b, '/': (a // b if b else 0)}[node[1]]
    raise ESError("%s must be a constant number" % what)


def known_names():
    return sorted(set(DRAW_CALLS) | UI_CALLS | CONFIG_CALLS | ACTION_CALLS | EXPR_FUNCS
                  | set(CALL_ALIASES) | BUILTIN_VARS)


def hint(name):
    close = difflib.get_close_matches(name, known_names(), n=1, cutoff=0.6)
    return " (did you mean '%s'?)" % close[0] if close else ""


# ----------------------------------------------------------------------------
# Program analysis
# ----------------------------------------------------------------------------
def is_true(cond):
    return cond[0] == 'num' and cond[1] != 0


def contains_ui(stmts):
    for s in stmts:
        if s[0] == 'call' and (CALL_ALIASES.get(s[1], s[1]) in DRAW_CALLS or s[1] in UI_CALLS):
            return True
        if s[0] == 'if' and (contains_ui(s[2]) or contains_ui(s[3])):
            return True
        if s[0] == 'while' and contains_ui(s[2]):
            return True
    return False


def contains_click(stmts):
    for s in stmts:
        if s[0] == 'call' and s[1] in UI_CALLS:
            return True
        if s[0] == 'if' and (contains_click(s[2]) or contains_click(s[3])):
            return True
        if s[0] == 'while' and contains_click(s[2]):
            return True
    return False


def view(stmts, kind, loop=False):
    """Split a block into what runs each frame ('update'), what draws ('paint')
    and what reacts to clicks ('click').

    A loop that contains draw commands (grids, star fields, ...) runs entirely
    at paint time; inside it (loop=True) only drawing and plain variable work
    is kept."""
    out = []
    for s in stmts:
        t = s[0]
        if t == 'call':
            name = CALL_ALIASES.get(s[1], s[1])
            if loop:
                if name in DRAW_CALLS:
                    out.append(s)
            elif kind == 'update':
                if name not in DRAW_CALLS and name not in UI_CALLS and name not in CONFIG_CALLS:
                    out.append(s)
            elif kind == 'paint':
                if name in DRAW_CALLS or name == 'button':
                    out.append(s)
            elif kind == 'click':
                if name in UI_CALLS:
                    out.append(s)
        elif t == 'assign' or t in ('break', 'continue'):
            if kind == 'update' or loop:
                out.append(s)
        elif t == 'if':
            a, b = view(s[2], kind, loop), view(s[3], kind, loop)
            if a or b:
                out.append(('if', s[1], a, b, s[4]))
        elif t == 'while':
            if loop:
                out.append(('while', s[1], view(s[2], kind, True), s[3],
                            view(s[4], kind, True), view(s[5], kind, True)))
            elif contains_click(s[2]):
                raise ESError("button/area commands can't be used inside a loop", s[3])
            elif contains_ui(s[2]):
                if kind == 'paint':
                    out.append(('while', s[1], view(s[2], kind, True), s[3],
                                view(s[4], kind, True), view(s[5], kind, True)))
            elif kind == 'update':
                out.append(s)
    return out


class Program:
    def __init__(self, src):
        raw = parse_source(src)
        self.fns = {}
        body = []
        for s in raw:
            if s[0] == 'fn':
                if s[1] in self.fns:
                    raise ESError("function '%s' is defined twice" % s[1], s[4])
                if s[1] in known_names():
                    raise ESError("'%s' is already a built-in name" % s[1], s[4])
                self.fns[s[1]] = s
            else:
                body.append(s)
        self.stmts = self._expand(body, [])
        self.cfg = {'title': 'ES Application', 'width': 900, 'height': 700,
                    'resizable': False, 'background': 0xFFFFFF, 'fps': 60}
        self.vars = []
        self.assigned = set()
        self.read = set()
        self.pressed_keys = []
        self._scan_config(self.stmts)
        main, pre = None, []
        for s in self.stmts:
            if s[0] == 'while' and is_true(s[1]):
                if main is not None:
                    raise ESError("only one main loop ('while true') is allowed", s[3])
                main = s
            else:
                pre.append(s)
        frame = main[2] if main else []
        self.init = view(pre, 'update')
        self.update = view(frame, 'update')
        self.paint = view(pre, 'paint') + view(frame, 'paint')
        self.click = view(pre, 'click') + view(frame, 'click')
        self._scan(self.stmts)
        for name in sorted(self.read - self.assigned):
            print("warning: variable '%s' is used but never assigned (it stays 0)" % name,
                  file=sys.stderr)

    # -- user functions ("fn") are inlined at every call ------------------------
    def _expand(self, stmts, stack):
        out = []
        for s in stmts:
            t = s[0]
            if t == 'fn':
                raise ESError("functions can only be defined at the top level", s[4])
            elif t == 'if':
                out.append(('if', s[1], self._expand(s[2], stack), self._expand(s[3], stack), s[4]))
            elif t == 'while':
                out.append(('while', s[1], self._expand(s[2], stack), s[3],
                            self._expand(s[4], stack), self._expand(s[5], stack)))
            elif t == 'call' and s[1] in self.fns:
                out.extend(self._inline(s, stack))
            elif t == 'call':
                out.append(self._expand_call(s, stack))
            else:
                out.append(s)
        return out

    def _expand_call(self, s, stack):
        name = CALL_ALIASES.get(s[1], s[1])
        args = []
        for k, v in s[2]:
            if v[0] == 'block':
                v = ('block', self._expand(v[1], stack))
            elif name in UI_CALLS and k == 'onclick' and v[0] == 'str':
                v = ('block', self._expand(parse_source(unescape(v[1]), s[3]), stack))
            args.append((k, v))
        return ('call', s[1], args, s[3])

    def _inline(self, s, stack):
        name, args, line = s[1], s[2], s[3]
        fn = self.fns[name]
        params = fn[2]
        if name in stack:
            raise ESError("function '%s' calls itself (recursion isn't supported)" % name, line)
        if any(k for k, _ in args):
            raise ESError("%s() takes plain (unnamed) arguments" % name, line)
        if len(args) != len(params):
            raise ESError("%s() takes %d argument%s but got %d"
                          % (name, len(params), '' if len(params) == 1 else 's', len(args)), line)
        out = []
        if len(params) == 1:
            out.append(('assign', params[0], args[0][1], line))
        else:                                   # evaluate every argument before assigning any
            for i, (_, e) in enumerate(args):
                out.append(('assign', '__a%d_%s' % (i, name), e, line))
            for i, p in enumerate(params):
                out.append(('assign', p, ('var', '__a%d_%s' % (i, name)), line))
        out.extend(self._expand(fn[3], stack + [name]))
        return out

    def _scan_config(self, stmts):
        for s in stmts:
            if s[0] != 'call':
                continue
            name = CALL_ALIASES.get(s[1], s[1])
            if name == 'resizable.enable':
                self.cfg['resizable'] = True
            elif name == 'resizable.disable':
                self.cfg['resizable'] = False
            elif name == 'window':
                for i, (k, v) in enumerate(s[2]):
                    k = k or ['title', 'width', 'height'][min(i, 2)]
                    if k == 'title':
                        if v[0] != 'str':
                            raise ESError("window title must be a string", s[3])
                        self.cfg['title'] = v[1].replace(LBRACE, '{').replace(RBRACE, '}')
                    elif k in ('width', 'height', 'fps'):
                        self.cfg[k] = max(1, const_eval(v, 'window ' + k))
                    elif k == 'resizable':
                        self.cfg['resizable'] = bool(const_eval(v, 'window resizable'))
                    elif k in ('background', 'bg'):
                        if v[0] == 'str':
                            self.cfg['background'] = parse_color(v[1], s[3])
                        else:
                            self.cfg['background'] = const_eval(v, 'window background')
                    else:
                        raise ESError("unknown window option '%s'" % k, s[3])

    def _scan(self, stmts):
        for s in stmts:
            t = s[0]
            if t == 'assign':
                self._declare(s[1], True)
                self._scan_expr(s[2])
            elif t == 'if':
                self._scan_expr(s[1])
                self._scan(s[2])
                self._scan(s[3])
            elif t == 'while':
                self._scan(s[5])
                self._scan_expr(s[1])
                self._scan(s[2])
                self._scan(s[4])
            elif t == 'call':
                name = CALL_ALIASES.get(s[1], s[1])
                if name in CONFIG_CALLS:
                    continue
                if name in UI_CALLS:
                    for k, v in bind_args(name, s[2], s[3]).items():
                        if k == 'onclick' and v[0] == 'str':
                            self._scan(parse_source(unescape(v[1]), s[3]))
                        elif v[0] == 'block':
                            self._scan(v[1])
                        else:
                            self._scan_expr(v)
                    continue
                for _, v in s[2]:
                    if v[0] == 'block':
                        self._scan(v[1])
                    else:
                        self._scan_expr(v)

    def _declare(self, name, assign):
        if name in BUILTIN_VARS:
            raise ESError("'%s' is read-only" % name)
        if name not in self.vars:
            self.vars.append(name)
        (self.assigned if assign else self.read).add(name)

    def _scan_expr(self, e):
        t = e[0]
        if t == 'var':
            if '.' in e[1] and e[1] not in BUILTIN_VARS:
                raise ESError("unknown value '%s'%s" % (e[1], hint(e[1])))
            if e[1] not in BUILTIN_VARS:
                self._declare(e[1], False)
        elif t == 'bin':
            self._scan_expr(e[2])
            self._scan_expr(e[3])
        elif t == 'un':
            self._scan_expr(e[2])
        elif t == 'tern':
            for sub in e[1:]:
                self._scan_expr(sub)
        elif t == 'str':
            for k, v in parse_interp(e[1]):
                if k == 'expr':
                    self._scan_expr(v)
        elif t == 'call':
            name = e[1]
            if name in ('key.down', 'key.pressed'):
                if len(e[2]) != 1:
                    raise ESError("%s takes one key name" % name, e[3])
                vk = key_code(e[2][0][1], e[3])
                if name == 'key.pressed' and vk not in self.pressed_keys:
                    self.pressed_keys.append(vk)
                return
            for _, v in e[2]:
                if v[0] == 'block':
                    self._scan(v[1])
                else:
                    self._scan_expr(v)


# ----------------------------------------------------------------------------
# PE import table
# ----------------------------------------------------------------------------
IMPORTS = [
    ('USER32.dll', ['RegisterClassExW', 'CreateWindowExW', 'ShowWindow', 'PeekMessageW',
                    'TranslateMessage', 'DispatchMessageW', 'DefWindowProcW', 'PostQuitMessage',
                    'BeginPaint', 'EndPaint', 'InvalidateRect', 'GetAsyncKeyState',
                    'GetForegroundWindow', 'FillRect', 'AdjustWindowRect', 'LoadCursorW',
                    'MessageBoxW', 'SetWindowTextW', 'MessageBeep']),
    ('GDI32.dll', ['TextOutW', 'Ellipse', 'Rectangle', 'RoundRect', 'MoveToEx', 'LineTo',
                   'CreateSolidBrush', 'CreatePen', 'GetStockObject', 'SelectObject',
                   'DeleteObject', 'SetTextColor', 'SetBkMode', 'SetTextAlign', 'CreateFontW',
                   'CreateCompatibleDC', 'CreateCompatibleBitmap', 'BitBlt', 'DeleteDC']),
    ('KERNEL32.dll', ['ExitProcess', 'Sleep', 'GetTickCount']),
]


class ImportBuilder:
    def __init__(self, base_rva):
        self.base = base_rva
        self.iat = {}
        d = bytearray(20 * (len(IMPORTS) + 1))
        ilt_pos, iat_pos, names = {}, {}, {}
        for dll, fns in IMPORTS:
            ilt_pos[dll] = len(d)
            d += b'\0' * (8 * (len(fns) + 1))
        for dll, fns in IMPORTS:
            iat_pos[dll] = len(d)
            for i, f in enumerate(fns):
                self.iat[(dll, f)] = base_rva + len(d) + 8 * i
            d += b'\0' * (8 * (len(fns) + 1))
        dll_name = {}
        for dll, fns in IMPORTS:
            dll_name[dll] = base_rva + len(d)
            d += dll.encode('ascii') + b'\0'
            for f in fns:
                if len(d) % 2:
                    d += b'\0'
                names[(dll, f)] = base_rva + len(d)
                d += b'\0\0' + f.encode('ascii') + b'\0'
        for k, (dll, fns) in enumerate(IMPORTS):
            for i, f in enumerate(fns):
                ent = struct.pack('<Q', names[(dll, f)])
                d[ilt_pos[dll] + 8 * i: ilt_pos[dll] + 8 * i + 8] = ent
                d[iat_pos[dll] + 8 * i: iat_pos[dll] + 8 * i + 8] = ent
            d[20 * k:20 * k + 20] = struct.pack('<IIIII', base_rva + ilt_pos[dll], 0, 0,
                                                 dll_name[dll], base_rva + iat_pos[dll])
        self.data = bytes(d)
        self.idt_size = 20 * (len(IMPORTS) + 1)


# ----------------------------------------------------------------------------
# Data section + assembler
# ----------------------------------------------------------------------------
class Data:
    def __init__(self, base):
        self.base = base
        self.buf = bytearray()
        self.strings = {}

    def alloc(self, size, align=8, init=b''):
        while len(self.buf) % align:
            self.buf.append(0)
        rva = self.base + len(self.buf)
        self.buf += init.ljust(size, b'\0')
        return rva

    def wstr(self, s):
        if s not in self.strings:
            self.strings[s] = self.alloc(0, 2, s.encode('utf-16-le') + b'\0\0')
        return self.strings[s]


JCC = {'o': 0, 'no': 1, 'b': 2, 'ae': 3, 'e': 4, 'ne': 5, 'be': 6, 'a': 7,
       's': 8, 'ns': 9, 'l': 0xC, 'ge': 0xD, 'le': 0xE, 'g': 0xF}
LEA_PREFIX = {'rax': b'\x48\x8d\x05', 'rcx': b'\x48\x8d\x0d', 'rdx': b'\x48\x8d\x15',
              'rsi': b'\x48\x8d\x35', 'rdi': b'\x48\x8d\x3d'}
ARG_REGS = [b'\x49\x8b\x4f', b'\x49\x8b\x57', b'\x4d\x8b\x47', b'\x4d\x8b\x4f']


class Assembler:
    def __init__(self, base):
        self.base = base
        self.code = bytearray()
        self.labels = {}
        self.fix = []

    def rva(self):
        return self.base + len(self.code)

    def label(self, name):
        assert name not in self.labels, name
        self.labels[name] = self.rva()

    def emit(self, b):
        self.code += b

    def rip(self, prefix, target):
        self.code += prefix
        self.code += struct.pack('<i', target - (self.rva() + 4))

    def ref(self, prefix, label):
        self.code += prefix
        self.fix.append((len(self.code), label))
        self.code += b'\0\0\0\0'

    def resolve(self):
        for pos, label in self.fix:
            self.code[pos:pos + 4] = struct.pack('<i', self.labels[label] - (self.base + pos + 4))

    # memory <-> register
    def load_rax(self, r): self.rip(b'\x48\x8b\x05', r)
    def store_rax(self, r): self.rip(b'\x48\x89\x05', r)
    def load_rcx(self, r): self.rip(b'\x48\x8b\x0d', r)
    def store_rcx(self, r): self.rip(b'\x48\x89\x0d', r)
    def lea(self, reg, r): self.rip(LEA_PREFIX[reg], r)
    def lea_rax_label(self, l): self.ref(b'\x48\x8d\x05', l)

    def imm_rax(self, v):
        if -2 ** 31 <= v < 2 ** 31:
            self.emit(b'\x48\xc7\xc0' + struct.pack('<i', v))
        else:
            self.emit(b'\x48\xb8' + struct.pack('<Q', v & 0xFFFFFFFFFFFFFFFF))

    def jmp(self, l): self.ref(b'\xe9', l)
    def jcc(self, cc, l): self.ref(b'\x0f' + bytes([0x80 + JCC[cc]]), l)
    def call_label(self, l): self.ref(b'\xe8', l)
    def call_iat(self, r): self.rip(b'\xff\x15', r)


# ----------------------------------------------------------------------------
# Code generator
# ----------------------------------------------------------------------------
class Gen:
    def __init__(self, prog, layout):
        self.prog = prog
        self.text_rva, self.rdata_rva, self.data_rva = layout
        self.ib = ImportBuilder(self.rdata_rva)
        self.data = Data(self.data_rva)
        self.asm = Assembler(self.text_rva)
        self.nlabel = 0
        self.mode = 'update'
        self.loops = []                  # (continue-label, break-label) of enclosing loops
        self._alloc_data()

    # -- data ---------------------------------------------------------------
    def _alloc_data(self):
        d, cfg = self.data, self.prog.cfg
        q = lambda init=0: d.alloc(8, 8, struct.pack('<q', init))
        self.g = {}
        for name in ('hwnd', 'mx', 'my', 'click', 'frame', 'seed', 'bg', 'wdc', 'mdc', 'bmp',
                     'obmp', 'hdc', 'len', 'font', 'ofont', 'brush', 'pen', 'ob', 'op',
                     'ww', 'wh'):
            self.g[name] = q()
        self.g['w'] = q(cfg['width'])
        self.g['h'] = q(cfg['height'])
        self.rc = d.alloc(16)
        self.rcwin = d.alloc(16, 8, struct.pack('<iiii', 0, 0, cfg['width'], cfg['height']))
        self.msg = d.alloc(48)
        self.ps = d.alloc(80)
        self.strbuf = d.alloc(1024, 8)
        self.class_rva = d.wstr('ESNativeClass5')
        self.title_rva = d.wstr(cfg['title'])
        self.font_rva = d.wstr('Segoe UI')
        wc = struct.pack('<IIQIIQQQQQQQ', 80, 3, 0, 0, 0, IMAGE_BASE, 0, 0, 0, 0,
                         IMAGE_BASE + self.class_rva, 0)
        self.wc = d.alloc(80, 8, wc)
        self.var = {n: q() for n in self.prog.vars}
        self.keyslots = {vk: (q(), q()) for vk in self.prog.pressed_keys}
        self.builtin = {'mouse.x': self.g['mx'], 'mouse_x': self.g['mx'],
                        'mouse.y': self.g['my'], 'mouse_y': self.g['my'],
                        'mouse.clicked': self.g['click'], 'window.w': self.g['w'],
                        'window.width': self.g['w'], 'window.h': self.g['h'],
                        'window.height': self.g['h'], 'frame': self.g['frame']}

    def new_label(self, base='L'):
        self.nlabel += 1
        return '%s%d' % (base, self.nlabel)

    # -- calling Windows ------------------------------------------------------
    def load_arg(self, arg):
        a = self.asm
        if isinstance(arg, int):
            a.imm_rax(arg)
        elif arg[0] == 'rva':
            a.lea('rax', arg[1])
        elif arg[0] == 'mem':
            a.load_rax(arg[1])
        elif arg[0] == 'local':
            a.emit(b'\x48\x8b\x45' + struct.pack('<b', arg[1]))
        elif arg[0] == 'expr':
            self.emit_expr(arg[1])
        else:
            raise AssertionError(arg)

    def call_api(self, dll, name, args=()):
        a = self.asm
        for arg in args:
            self.load_arg(arg)
            a.emit(b'\x50')                                   # push rax
        n = len(args)
        frame = (0x20 + 8 * max(0, n - 4) + 15) & ~15
        a.emit(b'\x49\x89\xe7')                               # mov r15,rsp
        a.emit(b'\x48\x83\xe4\xf0')                           # and rsp,-16
        a.emit(b'\x48\x83\xec' + bytes([frame]))              # sub rsp,frame
        for i in range(min(n, 4)):
            a.emit(ARG_REGS[i] + bytes([8 * (n - 1 - i)]))
        for i in range(4, n):
            a.emit(b'\x49\x8b\x47' + bytes([8 * (n - 1 - i)]))          # mov rax,[r15+d]
            a.emit(b'\x48\x89\x44\x24' + bytes([0x20 + 8 * (i - 4)]))   # mov [rsp+..],rax
        a.call_iat(self.ib.iat[(dll, name)])
        a.emit(b'\x4c\x89\xfc')                               # mov rsp,r15
        if n:
            a.emit(b'\x48\x83\xc4' + bytes([8 * n]))          # add rsp,8n

    def prologue(self):
        a = self.asm
        a.emit(b'\x55\x48\x89\xe5\x53\x56\x57\x41\x57')       # push rbp; mov rbp,rsp; push rbx,rsi,rdi,r15
        a.emit(b'\x48\x83\xec\x40')                           # sub rsp,0x40

    # -- expressions ------------------------------------------------------------
    def is_plain_var(self, node):
        if node[0] != 'var':
            return False
        return node[1] in self.var or node[1] in self.builtin

    def var_rva(self, name):
        return self.var[name] if name in self.var else self.builtin[name]

    def emit_expr(self, e):
        a = self.asm
        t = e[0]
        if t == 'num':
            a.imm_rax(e[1])
        elif t == 'var':
            name = e[1]
            if name in self.var or name in self.builtin:
                a.load_rax(self.var_rva(name))
            elif name == 'time.ms':
                self.call_api('KERNEL32.dll', 'GetTickCount')
                a.emit(b'\x89\xc0')                           # mov eax,eax
            elif name == 'mouse.down':
                self.emit_key_down(0x01)
            elif name == 'mouse.right':
                self.emit_key_down(0x02)
            else:
                raise ESError("unknown name '%s'%s" % (name, hint(name)))
        elif t == 'str':
            raise ESError("a string can't be used as a number here: \"%s\"" % e[1])
        elif t == 'un':
            self.emit_expr(e[2])
            if e[1] == '-':
                a.emit(b'\x48\xf7\xd8')                       # neg rax
            else:
                a.emit(b'\x48\x85\xc0\x0f\x94\xc0\x0f\xb6\xc0')   # test; sete al; movzx
        elif t == 'bin':
            self.emit_bin(e[1], e[2], e[3])
        elif t == 'tern':
            l_else, l_end = self.new_label('Te'), self.new_label('Tx')
            self.emit_expr(e[1])
            a.emit(b'\x48\x85\xc0')
            a.jcc('e', l_else)
            self.emit_expr(e[2])
            a.jmp(l_end)
            a.label(l_else)
            self.emit_expr(e[3])
            a.label(l_end)
        elif t == 'call':
            self.emit_func(e)
        else:
            raise AssertionError(e)

    def emit_bin(self, op, x, y):
        a = self.asm
        self.emit_expr(x)
        if y[0] == 'num' and -2 ** 31 <= y[1] < 2 ** 31:
            a.emit(b'\x48\xc7\xc1' + struct.pack('<i', y[1]))         # mov rcx,imm
        elif self.is_plain_var(y):
            a.load_rcx(self.var_rva(y[1]))
        else:
            a.emit(b'\x50')                                           # push rax
            self.emit_expr(y)
            a.emit(b'\x48\x89\xc1')                                   # mov rcx,rax
            a.emit(b'\x58')                                           # pop rax
        if op == '+':
            a.emit(b'\x48\x01\xc8')
        elif op == '-':
            a.emit(b'\x48\x29\xc8')
        elif op == '*':
            a.emit(b'\x48\x0f\xaf\xc1')
        elif op in ('/', '%'):
            a.emit(b'\x48\x85\xc9\x75\x07\x48\xc7\xc1\x01\x00\x00\x00')   # avoid divide by zero
            a.emit(b'\x48\x99\x48\xf7\xf9')                           # cqo; idiv rcx
            if op == '%':
                a.emit(b'\x48\x89\xd0')                               # mov rax,rdx
        elif op in ('==', '!=', '<', '<=', '>', '>='):
            cc = {'==': 0x94, '!=': 0x95, '<': 0x9C, '<=': 0x9E, '>': 0x9F, '>=': 0x9D}[op]
            a.emit(b'\x48\x39\xc8' + bytes([0x0f, cc, 0xc0]) + b'\x0f\xb6\xc0')
        elif op == '&&':
            a.emit(b'\x48\x85\xc0\x0f\x95\xc0\x48\x85\xc9\x0f\x95\xc1\x20\xc8\x0f\xb6\xc0')
        elif op == '||':
            a.emit(b'\x48\x85\xc0\x0f\x95\xc0\x48\x85\xc9\x0f\x95\xc1\x08\xc8\x0f\xb6\xc0')
        else:
            raise AssertionError(op)

    def emit_key_down(self, vk):
        a = self.asm
        l_no, l_end = self.new_label('Kn'), self.new_label('Kx')
        self.call_api('USER32.dll', 'GetForegroundWindow')
        a.rip(b'\x48\x3b\x05', self.g['hwnd'])                # cmp rax,[hwnd]
        a.jcc('ne', l_no)
        self.call_api('USER32.dll', 'GetAsyncKeyState', [vk])
        a.emit(b'\x25\x00\x80\x00\x00\xc1\xe8\x0f')           # and eax,0x8000; shr eax,15
        a.jmp(l_end)
        a.label(l_no)
        a.emit(b'\x31\xc0')
        a.label(l_end)

    def emit_func(self, e):
        a = self.asm
        name, args, line = e[1], e[2], e[3]
        pos = [v for k, v in args]
        if any(k for k, v in args):
            raise ESError("%s() takes plain (unnamed) arguments" % name, line)

        def need(n):
            if len(pos) != n:
                raise ESError("%s() takes %d argument%s" % (name, n, '' if n == 1 else 's'), line)
        if name == 'key.down':
            need(1)
            self.emit_key_down(key_code(pos[0], line))
        elif name == 'key.pressed':
            need(1)
            a.load_rax(self.keyslots[key_code(pos[0], line)][1])
        elif name in ('math.random', 'random'):
            need(2)
            self.emit_expr(pos[0])
            a.emit(b'\x50')
            self.emit_expr(pos[1])
            a.emit(b'\x59')                                   # pop rcx  (lo)
            a.call_label('rand_range')
        elif name == 'abs':
            need(1)
            self.emit_expr(pos[0])
            a.emit(b'\x48\x89\xc1\x48\xc1\xf9\x3f\x48\x31\xc8\x48\x29\xc8')
        elif name in ('min', 'max'):
            need(2)
            self.emit_expr(pos[0])
            a.emit(b'\x50')
            self.emit_expr(pos[1])
            a.emit(b'\x48\x89\xc1\x58\x48\x39\xc8')           # mov rcx,rax; pop rax; cmp rax,rcx
            a.emit(b'\x48\x0f\x4f\xc1' if name == 'min' else b'\x48\x0f\x4c\xc1')
        elif name == 'clamp':
            need(3)
            self.emit_expr(('call', 'min', [(None, ('call', 'max', [(None, pos[0]), (None, pos[1])], line)),
                                            (None, pos[2])], line))
        elif name == 'sign':
            need(1)
            self.emit_expr(pos[0])
            # rcx = x>>63 (-1 if x<0); rax = (-x)>>>63 (1 if x>0); result = rax | rcx
            a.emit(b'\x48\x89\xc1\x48\xc1\xf9\x3f\x48\xf7\xd8\x48\xc1\xe8\x3f\x48\x09\xc8')
        elif name == 'sq':
            need(1)
            self.emit_expr(('bin', '*', pos[0], pos[0]))
        elif name == 'dist':
            need(4)
            dx, dy = ('bin', '-', pos[2], pos[0]), ('bin', '-', pos[3], pos[1])
            self.emit_expr(('call', 'sqrt', [(None, ('bin', '+', ('bin', '*', dx, dx),
                                                     ('bin', '*', dy, dy)))], line))
        elif name == 'mouse.over':
            need(4)
            self.emit_expr(self.inside({'x': pos[0], 'y': pos[1], 'w': pos[2], 'h': pos[3]}))
        elif name == 'sqrt':
            need(1)
            self.emit_expr(pos[0])
            a.emit(b'\xf2\x48\x0f\x2a\xc0\xf2\x0f\x51\xc0\xf2\x48\x0f\x2c\xc0')
        elif name == 'rgb':
            need(3)
            self.emit_expr(pos[0])
            a.emit(b'\x50')
            self.emit_expr(pos[1])
            a.emit(b'\x50')
            self.emit_expr(pos[2])
            a.emit(b'\x48\xc1\xe0\x10\x59\x48\xc1\xe1\x08\x48\x09\xc8\x59\x48\x09\xc8')
        else:
            raise ESError("unknown function '%s'%s" % (name, hint(name)), line)

    # -- text helpers ------------------------------------------------------------
    def compose(self, node, line):
        """Build an interpolated string into strbuf; length (chars) goes to g['len']."""
        a = self.asm
        segs = parse_interp(node[1], line) if node[0] == 'str' else [('expr', node)]
        a.lea('rdi', self.strbuf)
        total = 0
        for kind, val in segs:
            if kind == 'lit':
                n = len(val.encode('utf-16-le')) // 2
                if not n:
                    continue
                a.lea('rsi', self.data.wstr(val))
                a.emit(b'\xb9' + struct.pack('<I', n))        # mov ecx,n
                a.emit(b'\xf3\x66\xa5')                       # rep movsw
                total += n
            else:
                self.emit_expr(val)
                a.call_label('itoa')
                total += 21
        if total > 500:
            raise ESError("text is too long", line)
        a.emit(b'\x31\xc0\x66\x89\x07')                       # terminator
        a.emit(b'\x48\x89\xf8')                               # mov rax,rdi
        a.lea('rcx', self.strbuf)
        a.emit(b'\x48\x29\xc8\x48\xd1\xe8')                   # sub rax,rcx; shr rax,1
        a.store_rax(self.g['len'])

    def color_node(self, node, default, line, hollow=False):
        if node is None:
            return ('num', default)
        if node[0] == 'str':
            s = node[1].replace(LBRACE, '{')
            if s.strip().lower() in ('none', 'transparent'):
                if hollow:
                    return ('hollow',)
                raise ESError("'%s' can only be used as the fill colour of a shape" % s, line)
            return ('num', parse_color(s, line))
        if node[0] == 'tern':                    # cond ? "red" : "#333"
            return ('tern', node[1], self.color_node(node[2], default, line),
                    self.color_node(node[3], default, line))
        return node

    def bind(self, name, args, line):
        return bind_args(name, args, line)

    # -- statements ---------------------------------------------------------------
    def emit_block(self, stmts):
        for s in stmts:
            self.emit_stmt(s)

    def emit_stmt(self, s):
        a = self.asm
        t = s[0]
        if t == 'assign':
            self.emit_expr(s[2])
            a.store_rax(self.var[s[1]])
        elif t == 'if':
            l_else, l_end = self.new_label('Ie'), self.new_label('Ix')
            self.emit_expr(s[1])
            a.emit(b'\x48\x85\xc0')
            a.jcc('e', l_else)
            self.emit_block(s[2])
            if s[3]:
                a.jmp(l_end)
            a.label(l_else)
            if s[3]:
                self.emit_block(s[3])
                a.label(l_end)
        elif t == 'while':
            if is_true(s[1]):
                raise ESError("an endless loop is only allowed as the main loop", s[3])
            l_top, l_cont, l_end = self.new_label('Wt'), self.new_label('Wc'), self.new_label('Wx')
            self.emit_block(s[5])                       # for/repeat set-up
            a.label(l_top)
            self.emit_expr(s[1])
            a.emit(b'\x48\x85\xc0')
            a.jcc('e', l_end)
            self.loops.append((l_cont, l_end))
            self.emit_block(s[2])
            self.loops.pop()
            a.label(l_cont)
            self.emit_block(s[4])                       # for/repeat step
            a.jmp(l_top)
            a.label(l_end)
        elif t in ('break', 'continue'):
            if not self.loops:
                raise ESError("'%s' can only be used inside a loop" % t, s[1])
            cont, brk = self.loops[-1]
            if t == 'continue':
                a.jmp(cont)
            elif brk is None:
                raise ESError("'break' can't be used directly in the main loop "
                              "(use exit() to quit)", s[1])
            else:
                a.jmp(brk)
        elif t == 'call':
            self.emit_call(s)

    def emit_call(self, s):
        a = self.asm
        name, args, line = CALL_ALIASES.get(s[1], s[1]), s[2], s[3]
        if name in CONFIG_CALLS:
            return
        if name in PARAMS:
            if self.mode == 'click' and name in UI_CALLS:
                return self.emit_click(name, args, line)
            if self.mode == 'paint' and name in DRAW_CALLS | {'button'}:
                return self.emit_draw(name, args, line)
            return
        if name == 'exit':
            self.call_api('USER32.dll', 'PostQuitMessage', [0])
        elif name == 'beep':
            self.call_api('USER32.dll', 'MessageBeep', [0])
        elif name in ('alert', 'title'):
            if len(args) != 1:
                raise ESError("%s() takes one text argument" % name, line)
            self.compose(args[0][1], line)
            if name == 'title':
                self.call_api('USER32.dll', 'SetWindowTextW', [('mem', self.g['hwnd']),
                                                               ('rva', self.strbuf)])
            else:
                self.call_api('USER32.dll', 'MessageBoxW', [('mem', self.g['hwnd']),
                                                            ('rva', self.strbuf),
                                                            ('rva', self.title_rva), 0x40])
        else:
            raise ESError("unknown command '%s'%s" % (s[1], hint(s[1])), line)

    # click handling ---------------------------------------------------------------
    def onclick_stmts(self, node, line):
        if node is None:
            return []
        if node[0] == 'block':
            stmts = node[1]
        elif node[0] == 'str':
            stmts = parse_source(node[1].replace(LBRACE, '{').replace(RBRACE, '}'), line)
        else:
            raise ESError("onclick must be a { block } or a string of statements", line)
        if contains_ui(stmts):
            raise ESError("draw/button commands can't be used inside onclick", line)
        return view(stmts, 'update')

    @staticmethod
    def inside(p):
        mx, my = ('var', 'mouse.x'), ('var', 'mouse.y')
        x, y, w, h = p['x'], p['y'], p['w'], p['h']
        both = lambda u, v: ('bin', '&&', u, v)
        return both(both(('bin', '>=', mx, x), ('bin', '<', mx, ('bin', '+', x, w))),
                    both(('bin', '>=', my, y), ('bin', '<', my, ('bin', '+', y, h))))

    def emit_click(self, name, args, line):
        p = self.bind(name, args, line)
        for k in ('x', 'y', 'w', 'h'):
            if k not in p:
                raise ESError("%s needs %s" % (name, k), line)
        body = self.onclick_stmts(p.get('onclick'), line)
        l_skip = self.new_label('Cs')
        self.emit_expr(self.inside(p))
        self.asm.emit(b'\x48\x85\xc0')
        self.asm.jcc('e', l_skip)
        self.emit_block(body)
        self.asm.label(l_skip)

    # drawing ------------------------------------------------------------------------
    def hdc(self):
        return ('mem', self.g['hdc'])

    def select_in(self, obj_slot, old_slot):
        self.call_api('GDI32.dll', 'SelectObject', [self.hdc(), ('mem', obj_slot)])
        self.asm.store_rax(old_slot)

    def emit_draw(self, name, args, line):
        p = self.bind(name, args, line)
        g = self.g
        num = lambda v: ('num', v)
        add = lambda u, v: ('bin', '+', u, v)
        sub = lambda u, v: ('bin', '-', u, v)

        def req(*ks):
            for k in ks:
                if k not in p:
                    raise ESError("%s needs '%s'" % (name, k), line)
        if name == 'draw.text':
            req('x', 'y', 'text')
            weight = add(num(400), ('bin', '*', p.get('bold', num(0)), num(300)))
            center = 0
            if p.get('align') is not None:
                al = p['align']
                if al[0] != 'str' or al[1] not in ('left', 'center', 'right'):
                    raise ESError('align must be "left", "center" or "right"', line)
                center = {'left': 0, 'center': 6, 'right': 2}[al[1]]
            self.emit_text(p['x'], p['y'], p['text'], self.color_node(p.get('color'), 0, line),
                           p.get('size', num(20)), weight, center, line)
        elif name == 'button':
            req('x', 'y', 'w', 'h', 'text')
            base = parse_color(p['color'][1], line) if p.get('color') and p['color'][0] == 'str' else 0xCC6633
            size = p.get('size', num(20))
            hover = self.inside(p)
            pressed = ('bin', '&&', hover, ('var', 'mouse.down'))
            col = ('tern', pressed, num(shade(base, -35)), ('tern', hover, num(shade(base, 30)), num(base)))
            self.emit_shape('draw.roundrect', p['x'], p['y'], p['w'], p['h'], col, num(14), None, line)
            cx = add(p['x'], ('bin', '/', p['w'], num(2)))
            cy = add(p['y'], ('bin', '/', sub(('bin', '*', p['h'], num(5)), ('bin', '*', size, num(6))), num(10)))
            self.emit_text(cx, cy, p['text'], num(0xFFFFFF), size, num(700), 6, line)
        elif name == 'draw.rect':
            req('x', 'y', 'w', 'h')
            self.emit_shape(name, p['x'], p['y'], p['w'], p['h'], self.color_node(p.get('color'), 0x00FF00, line, True),
                            None, self.opt_color(p.get('outline'), line), line)
        elif name == 'draw.ellipse':
            req('x', 'y', 'w', 'h')
            self.emit_shape(name, p['x'], p['y'], p['w'], p['h'],
                            self.color_node(p.get('color'), 0x00FF00, line, True),
                            None, self.opt_color(p.get('outline'), line), line)
        elif name == 'draw.clear':
            self.emit_shape('draw.rect', num(0), num(0), ('var', 'window.w'), ('var', 'window.h'),
                            self.color_node(p.get('color'), 0xFFFFFF, line), None, None, line)
        elif name == 'draw.bar':
            req('x', 'y', 'w', 'h', 'value')
            top = p.get('max', num(100))
            back = self.color_node(p.get('back'), 0x333333, line)
            self.emit_shape('draw.rect', p['x'], p['y'], p['w'], p['h'], back, None, None, line)
            val = ('call', 'clamp', [(None, p['value']), (None, num(0)), (None, top)], line)
            fill_w = ('bin', '/', ('bin', '*', p['w'], val), top)
            l_skip = self.new_label('Bs')
            self.emit_expr(fill_w)
            self.asm.emit(b'\x48\x85\xc0')
            self.asm.jcc('e', l_skip)                 # nothing to fill when the value is 0
            self.emit_shape('draw.rect', p['x'], p['y'], fill_w, p['h'],
                            self.color_node(p.get('color'), 0x00C800, line), None, None, line)
            self.asm.label(l_skip)
        elif name == 'draw.roundrect':
            req('x', 'y', 'w', 'h')
            self.emit_shape(name, p['x'], p['y'], p['w'], p['h'], self.color_node(p.get('color'), 0x00FF00, line, True),
                            p.get('radius', num(16)), self.opt_color(p.get('outline'), line), line)
        elif name == 'draw.circle':
            req('x', 'y', 'r')
            self.emit_shape(name, p['x'], p['y'], p['r'], None, self.color_node(p.get('color'), 0x0000FF, line, True),
                            None, self.opt_color(p.get('outline'), line), line)
        elif name == 'draw.line':
            req('x1', 'y1', 'x2', 'y2')
            col = self.color_node(p.get('color'), 0, line)
            self.call_api('GDI32.dll', 'CreatePen', [0, ('expr', p.get('width', num(1))), ('expr', col)])
            self.asm.store_rax(self.g['pen'])
            self.select_in(self.g['pen'], self.g['op'])
            self.call_api('GDI32.dll', 'MoveToEx', [self.hdc(), ('expr', p['x1']), ('expr', p['y1']), 0])
            self.call_api('GDI32.dll', 'LineTo', [self.hdc(), ('expr', p['x2']), ('expr', p['y2'])])
            self.call_api('GDI32.dll', 'SelectObject', [self.hdc(), ('mem', self.g['op'])])
            self.call_api('GDI32.dll', 'DeleteObject', [('mem', self.g['pen'])])

    def opt_color(self, node, line):
        return None if node is None else self.color_node(node, 0, line)

    def emit_shape(self, name, x, y, a1, a2, color, radius, outline, line):
        g, asm = self.g, self.asm
        one = ('num', 1)
        add = lambda u, v: ('bin', '+', u, v)
        sub = lambda u, v: ('bin', '-', u, v)
        hollow = color[0] == 'hollow'
        if hollow:
            self.call_api('GDI32.dll', 'GetStockObject', [5])          # NULL_BRUSH: outline only
        else:
            self.call_api('GDI32.dll', 'CreateSolidBrush', [('expr', color)])
        asm.store_rax(g['brush'])
        if outline is None:
            self.call_api('GDI32.dll', 'GetStockObject', [8])        # NULL_PEN
        else:
            self.call_api('GDI32.dll', 'CreatePen', [0, 1, ('expr', outline)])
        asm.store_rax(g['pen'])
        self.select_in(g['brush'], g['ob'])
        self.select_in(g['pen'], g['op'])
        extra = 0 if outline is not None else 1
        if name == 'draw.circle':
            args = [self.hdc(), ('expr', sub(x, a1)), ('expr', sub(y, a1)),
                    ('expr', add(add(x, a1), ('num', extra))), ('expr', add(add(y, a1), ('num', extra)))]
            self.call_api('GDI32.dll', 'Ellipse', args)
        else:
            args = [self.hdc(), ('expr', x), ('expr', y),
                    ('expr', add(add(x, a1), ('num', extra))), ('expr', add(add(y, a2), ('num', extra)))]
            if name == 'draw.roundrect':
                args += [('expr', radius), ('expr', radius)]
                self.call_api('GDI32.dll', 'RoundRect', args)
            elif name == 'draw.ellipse':
                self.call_api('GDI32.dll', 'Ellipse', args)
            else:
                self.call_api('GDI32.dll', 'Rectangle', args)
        self.call_api('GDI32.dll', 'SelectObject', [self.hdc(), ('mem', g['ob'])])
        self.call_api('GDI32.dll', 'SelectObject', [self.hdc(), ('mem', g['op'])])
        if not hollow:
            self.call_api('GDI32.dll', 'DeleteObject', [('mem', g['brush'])])
        if outline is not None:
            self.call_api('GDI32.dll', 'DeleteObject', [('mem', g['pen'])])

    def emit_text(self, x, y, text, color, size, weight, center, line):
        g = self.g
        self.compose(text, line)
        neg = ('bin', '-', ('num', 0), size)
        self.call_api('GDI32.dll', 'CreateFontW', [('expr', neg), 0, 0, 0, ('expr', weight),
                                                   0, 0, 0, 1, 0, 0, 5, 0, ('rva', self.font_rva)])
        self.asm.store_rax(g['font'])
        self.select_in(g['font'], g['ofont'])
        self.call_api('GDI32.dll', 'SetTextColor', [self.hdc(), ('expr', color)])
        if center:
            self.call_api('GDI32.dll', 'SetTextAlign', [self.hdc(), center])
        self.call_api('GDI32.dll', 'TextOutW', [self.hdc(), ('expr', x), ('expr', y),
                                                ('rva', self.strbuf), ('mem', g['len'])])
        if center:
            self.call_api('GDI32.dll', 'SetTextAlign', [self.hdc(), 0])
        self.call_api('GDI32.dll', 'SelectObject', [self.hdc(), ('mem', g['ofont'])])
        self.call_api('GDI32.dll', 'DeleteObject', [('mem', g['font'])])

    # -- whole program ---------------------------------------------------------------------
    def generate(self):
        a, g, cfg = self.asm, self.g, self.prog.cfg
        style = 0x00CF0000 if cfg['resizable'] else 0x00CA0000

        # ---------------- entry point ----------------
        a.label('Entry')
        self.prologue()
        self.call_api('USER32.dll', 'LoadCursorW', [0, 32512])
        a.store_rax(self.wc + 40)
        a.lea_rax_label('WndProc')
        a.store_rax(self.wc + 8)
        self.call_api('USER32.dll', 'RegisterClassExW', [('rva', self.wc)])
        self.call_api('GDI32.dll', 'CreateSolidBrush', [cfg['background']])
        a.store_rax(g['bg'])
        self.call_api('KERNEL32.dll', 'GetTickCount')
        a.emit(b'\x48\xb9' + struct.pack('<Q', 0x9E3779B97F4A7C15))
        a.emit(b'\x48\x0f\xaf\xc1\x48\x83\xc8\x01')                  # imul rax,rcx; or rax,1
        a.store_rax(g['seed'])
        self.mode = 'update'
        self.emit_block(self.prog.init)
        self.call_api('USER32.dll', 'AdjustWindowRect', [('rva', self.rcwin), style, 0])
        for off, slot in ((8, 'ww'), (12, 'wh')):
            lo = 0 if off == 8 else 4
            a.rip(b'\x8b\x05', self.rcwin + off)                     # mov eax,[right/bottom]
            a.rip(b'\x2b\x05', self.rcwin + lo)                      # sub eax,[left/top]
            a.store_rax(g[slot])
        self.call_api('USER32.dll', 'CreateWindowExW',
                      [0, ('rva', self.class_rva), ('rva', self.title_rva), style,
                       0x80000000, 0x80000000, ('mem', g['ww']), ('mem', g['wh']),
                       0, 0, IMAGE_BASE, 0])
        a.store_rax(g['hwnd'])
        a.emit(b'\x48\x85\xc0')
        a.jcc('e', 'Exit')
        self.call_api('USER32.dll', 'ShowWindow', [('mem', g['hwnd']), 5])

        a.label('MessageLoop')
        self.call_api('USER32.dll', 'PeekMessageW', [('rva', self.msg), 0, 0, 0, 1])
        a.emit(b'\x85\xc0')
        a.jcc('e', 'GameUpdate')
        a.rip(b'\x8b\x05', self.msg + 8)                             # mov eax,[msg.message]
        a.emit(b'\x3d\x12\x00\x00\x00')                              # WM_QUIT?
        a.jcc('e', 'Exit')
        self.call_api('USER32.dll', 'TranslateMessage', [('rva', self.msg)])
        self.call_api('USER32.dll', 'DispatchMessageW', [('rva', self.msg)])
        a.jmp('MessageLoop')

        a.label('GameUpdate')
        a.load_rax(g['frame'])
        a.emit(b'\x48\x83\xc0\x01')
        a.store_rax(g['frame'])
        for vk, (prev, flag) in self.keyslots.items():
            self.emit_key_down(vk)
            a.load_rcx(prev)
            a.store_rax(prev)
            a.emit(b'\x48\x83\xf1\x01\x48\x21\xc8')                  # xor rcx,1; and rax,rcx
            a.store_rax(flag)
        self.mode = 'update'
        self.loops = [('FrameEnd', None)]                            # 'continue' skips to the frame end
        self.emit_block(self.prog.update)
        self.loops = []
        a.label('FrameEnd')
        a.emit(b'\x31\xc0')
        a.store_rax(g['click'])
        self.call_api('USER32.dll', 'InvalidateRect', [('mem', g['hwnd']), 0, 0])
        self.call_api('KERNEL32.dll', 'Sleep', [max(1, 1000 // cfg['fps'])])
        a.jmp('MessageLoop')

        a.label('Exit')
        self.call_api('KERNEL32.dll', 'ExitProcess', [0])

        # ---------------- window procedure ----------------
        a.label('WndProc')
        self.prologue()
        a.emit(b'\x48\x89\x4d\xd8\x48\x89\x55\xd0\x4c\x89\x45\xc8\x4c\x89\x4d\xc0')
        a.emit(b'\x8b\x45\xd0')                                      # mov eax,[rbp-0x30]  (message)
        for m, lab in ((0x0F, 'W_Paint'), (0x14, 'W_Erase'), (0x200, 'W_Move'),
                       (0x201, 'W_Down'), (0x05, 'W_Size'), (0x02, 'W_Destroy')):
            a.emit(b'\x3d' + struct.pack('<I', m))
            a.jcc('e', lab)
        self.call_api('USER32.dll', 'DefWindowProcW',
                      [('local', -0x28), ('local', -0x30), ('local', -0x38), ('local', -0x40)])
        a.jmp('W_End')

        a.label('W_Erase')
        a.emit(b'\xb8\x01\x00\x00\x00')
        a.jmp('W_End')

        a.label('W_Move')
        self.mouse_from_lparam()
        a.emit(b'\x31\xc0')
        a.jmp('W_End')

        a.label('W_Size')
        a.emit(b'\x48\x8b\x45\xc0\x0f\xb7\xc8')                      # mov rax,[lParam]; movzx ecx,ax
        a.store_rcx(g['w'])
        a.emit(b'\x48\xc1\xe8\x10\x0f\xb7\xc8')
        a.store_rcx(g['h'])
        a.emit(b'\x31\xc0')
        a.jmp('W_End')

        a.label('W_Down')
        self.mouse_from_lparam()
        a.emit(b'\x48\xc7\xc0\x01\x00\x00\x00')
        a.store_rax(g['click'])
        self.mode = 'click'
        self.emit_block(self.prog.click)
        self.call_api('USER32.dll', 'InvalidateRect', [('mem', g['hwnd']), 0, 0])
        a.emit(b'\x31\xc0')
        a.jmp('W_End')

        a.label('W_Destroy')
        self.call_api('USER32.dll', 'PostQuitMessage', [0])
        a.emit(b'\x31\xc0')
        a.jmp('W_End')

        a.label('W_Paint')
        self.call_api('USER32.dll', 'BeginPaint', [('local', -0x28), ('rva', self.ps)])
        a.store_rax(g['wdc'])
        for dim in ('w', 'h'):
            a.load_rax(g[dim])
            a.emit(b'\x48\x85\xc0')
            a.jcc('e', 'P_Done')
        self.call_api('GDI32.dll', 'CreateCompatibleDC', [('mem', g['wdc'])])
        a.store_rax(g['mdc'])
        a.store_rax(g['hdc'])
        self.call_api('GDI32.dll', 'CreateCompatibleBitmap', [('mem', g['wdc']), ('mem', g['w']), ('mem', g['h'])])
        a.store_rax(g['bmp'])
        self.call_api('GDI32.dll', 'SelectObject', [('mem', g['mdc']), ('mem', g['bmp'])])
        a.store_rax(g['obmp'])
        a.load_rax(g['w'])
        a.rip(b'\x89\x05', self.rc + 8)                              # mov [rc.right],eax
        a.load_rax(g['h'])
        a.rip(b'\x89\x05', self.rc + 12)
        self.call_api('USER32.dll', 'FillRect', [('mem', g['mdc']), ('rva', self.rc), ('mem', g['bg'])])
        self.call_api('GDI32.dll', 'SetBkMode', [('mem', g['mdc']), 1])
        self.mode = 'paint'
        self.emit_block(self.prog.paint)
        self.call_api('GDI32.dll', 'BitBlt', [('mem', g['wdc']), 0, 0, ('mem', g['w']), ('mem', g['h']),
                                              ('mem', g['mdc']), 0, 0, 0x00CC0020])
        self.call_api('GDI32.dll', 'SelectObject', [('mem', g['mdc']), ('mem', g['obmp'])])
        self.call_api('GDI32.dll', 'DeleteObject', [('mem', g['bmp'])])
        self.call_api('GDI32.dll', 'DeleteDC', [('mem', g['mdc'])])
        a.label('P_Done')
        self.call_api('USER32.dll', 'EndPaint', [('local', -0x28), ('rva', self.ps)])
        a.emit(b'\x31\xc0')

        a.label('W_End')
        a.emit(b'\x48\x8d\x65\xe0\x41\x5f\x5f\x5e\x5b\x5d\xc3')      # lea rsp,[rbp-0x20]; pops; ret

        # ---------------- runtime helpers ----------------
        a.label('itoa')                                              # rax -> UTF-16 digits at [rdi]
        neg = b'\x66\xc7\x07\x2d\x00\x48\x83\xc7\x02\x48\xf7\xd8'
        a.emit(b'\x48\x85\xc0\x79' + bytes([len(neg)]) + neg)
        a.emit(b'\xb9\x0a\x00\x00\x00\x45\x31\xc0')
        loop = b'\x31\xd2\x48\xf7\xf1\x80\xc2\x30\x52\x49\xff\xc0\x48\x85\xc0'
        a.emit(loop + b'\x75' + struct.pack('<b', -(len(loop) + 2)))
        out = b'\x5a\x66\x89\x17\x48\x83\xc7\x02\x49\xff\xc8'
        a.emit(out + b'\x75' + struct.pack('<b', -(len(out) + 2)))
        a.emit(b'\xc3')

        a.label('rand_range')                                        # rcx=lo, rax=hi -> rax
        a.emit(b'\x49\x89\xc0\x49\x29\xc8\x49\xff\xc0\x4d\x85\xc0\x7f\x06\x41\xb8\x01\x00\x00\x00')
        a.load_rax(g['seed'])
        a.emit(b'\x48\x89\xc2\x48\xc1\xe2\x0d\x48\x31\xd0')
        a.emit(b'\x48\x89\xc2\x48\xc1\xea\x07\x48\x31\xd0')
        a.emit(b'\x48\x89\xc2\x48\xc1\xe2\x11\x48\x31\xd0')
        a.store_rax(g['seed'])
        a.emit(b'\x48\xd1\xe8\x31\xd2\x49\xf7\xf0\x48\x8d\x04\x11\xc3')
        a.resolve()

    def mouse_from_lparam(self):
        a, g = self.asm, self.g
        a.emit(b'\x48\x8b\x45\xc0\x48\x0f\xbf\xc8')                  # mov rax,[lParam]; movsx rcx,ax
        a.store_rcx(g['mx'])
        a.emit(b'\x48\xc1\xe8\x10\x48\x0f\xbf\xc8')
        a.store_rcx(g['my'])


# ----------------------------------------------------------------------------
# PE writer
# ----------------------------------------------------------------------------
def align(v, a):
    return (v + a - 1) // a * a


def build(prog):
    # pass 1 measures the sections, pass 2 lays them out for real
    gen = Gen(prog, (0x1000, 0x2000, 0x3000))
    gen.generate()
    text_rva = 0x1000
    rdata_rva = text_rva + align(len(gen.asm.code), 0x1000)
    data_rva = rdata_rva + align(len(gen.ib.data), 0x1000)
    gen = Gen(prog, (text_rva, rdata_rva, data_rva))
    gen.generate()
    code, rdata, data = bytes(gen.asm.code), gen.ib.data, bytes(gen.data.buf)
    assert text_rva + align(len(code), 0x1000) == rdata_rva

    FA, SA, hdr = 0x200, 0x1000, 0x200
    t_raw, r_raw, d_raw = align(len(code), FA), align(len(rdata), FA), align(len(data), FA)
    size_of_image = data_rva + align(len(data), SA)
    dos = bytearray(0x80)
    dos[0:2] = b'MZ'
    dos[0x3C:0x40] = struct.pack('<I', 0x80)
    coff = struct.pack('<HHIIIHH', 0x8664, 3, 0, 0, 0, 0xF0, 0x0022)
    dirs = bytearray(128)
    dirs[8:16] = struct.pack('<II', rdata_rva, gen.ib.idt_size)
    opt = struct.pack('<HBBIIIIIQIIHHHHHHIIIIHHQQQQII',
                      0x020B, 14, 0, t_raw, r_raw + d_raw, 0, gen.asm.labels['Entry'],
                      text_rva, IMAGE_BASE, SA, FA, 6, 0, 0, 0, 6, 0, 0, size_of_image, hdr, 0,
                      2, 0x8100, 0x100000, 0x1000, 0x100000, 0x1000, 0, 16) + bytes(dirs)

    def section(name, vsize, va, rsize, rptr, flags):
        return name.ljust(8, '\0').encode() + struct.pack('<IIIIIIHHI', vsize, va, rsize, rptr, 0, 0, 0, 0, flags)
    table = (section('.text', len(code), text_rva, t_raw, hdr, 0x60000020) +
             section('.rdata', len(rdata), rdata_rva, r_raw, hdr + t_raw, 0x40000040) +
             section('.data', len(data), data_rva, d_raw, hdr + t_raw + r_raw, 0xC0000040))
    pe = bytes(dos) + b'PE\0\0' + coff + opt + table
    assert len(pe) <= hdr
    return (pe.ljust(hdr, b'\0') + code.ljust(t_raw, b'\0') + rdata.ljust(r_raw, b'\0')
            + data.ljust(d_raw, b'\0'))


def compile_source(src):
    return build(Program(src))


USAGE = """ESEX %s - native Windows compiler for ES scripts

usage: esex <source.es> [-o output.exe] [--check] [--run]

  -o FILE        name of the .exe to write (default: <source>.exe)
  --check, -c    only check the script for errors, write nothing
  --run, -r      start the program after compiling (Windows only)
  -v, --version  print the version
  -h, --help     show this help"""


def show_error(path, e, src):
    print("%s: error: %s" % (path, e), file=sys.stderr)
    if e.line and src:
        lines = src.splitlines()
        if 1 <= e.line <= len(lines):
            print("  %4d | %s" % (e.line, lines[e.line - 1].strip()), file=sys.stderr)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(USAGE % VERSION)
        return 1
    if '-v' in argv or '--version' in argv or argv[0] == 'version':
        print("esex " + VERSION)
        return 0
    if '-h' in argv or '--help' in argv:
        print(USAGE % VERSION)
        return 0
    out = None
    if '-o' in argv:
        i = argv.index('-o')
        if i + 1 >= len(argv):
            print("error: -o needs a file name", file=sys.stderr)
            return 1
        out = argv[i + 1]
        del argv[i:i + 2]
    check = run = False
    rest = []
    for arg in argv:
        if arg in ('--check', '-c'):
            check = True
        elif arg in ('--run', '-r'):
            run = True
        elif arg.startswith('-') and len(arg) > 1:
            print("error: unknown option '%s' (try esex --help)" % arg, file=sys.stderr)
            return 1
        else:
            rest.append(arg)
    if len(rest) != 1:
        print("error: give exactly one source file (try esex --help)", file=sys.stderr)
        return 1
    src_path = rest[0]
    out = out or os.path.splitext(src_path)[0] + '.exe'
    src = ''
    try:
        with open(src_path, 'r', encoding='utf-8-sig') as f:
            src = f.read()
        pe = compile_source(src)
    except OSError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    except ESError as e:
        show_error(src_path, e, src)
        return 1
    if check:
        print("%s: OK" % src_path)
        return 0
    with open(out, 'wb') as f:
        f.write(pe)
    print("Compiled %s -> %s (%d bytes)" % (src_path, out, len(pe)))
    if run:
        if os.name != 'nt':
            print("note: --run only works on Windows", file=sys.stderr)
            return 0
        import subprocess
        subprocess.Popen([os.path.abspath(out)])
    return 0


if __name__ == '__main__':
    sys.exit(main())