"""ESEX test-suite.  Run with:  python -m unittest discover tests -v

The language semantics are checked with a tiny reference interpreter that runs
the compiler's own AST, so no Windows machine is needed.  The compiled output
is checked structurally (PE headers, every example compiles).
"""
import contextlib
import glob
import io
import math
import os
import sys
import unittest
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import esex  # noqa: E402


class _Break(Exception):
    pass


class _Continue(Exception):
    pass


def _idiv(a, b):
    b = b or 1
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


class Machine:
    """Runs Program.init and Program.update like the compiled exe would."""

    def __init__(self, src, keys=()):
        self.prog = esex.Program(src)
        self.env = defaultdict(int)
        self.keys = set(keys)
        self.block(self.prog.init)

    def frame(self, n=1):
        for _ in range(n):
            try:
                self.block(self.prog.update)
            except _Continue:
                pass
        return self

    def block(self, stmts):
        for s in stmts:
            self.stmt(s)

    def stmt(self, s):
        t = s[0]
        if t == 'assign':
            self.env[s[1]] = self.ev(s[2])
        elif t == 'if':
            self.block(s[2] if self.ev(s[1]) else s[3])
        elif t == 'while':
            self.block(s[5])
            while self.ev(s[1]):
                try:
                    self.block(s[2])
                except _Break:
                    break
                except _Continue:
                    pass
                self.block(s[4])
        elif t == 'break':
            raise _Break()
        elif t == 'continue':
            raise _Continue()

    def ev(self, e):
        t = e[0]
        if t == 'num':
            return e[1]
        if t == 'var':
            return self.env[e[1]]
        if t == 'un':
            v = self.ev(e[2])
            return -v if e[1] == '-' else int(not v)
        if t == 'tern':
            return self.ev(e[2]) if self.ev(e[1]) else self.ev(e[3])
        if t == 'bin':
            op, a, b = e[1], self.ev(e[2]), self.ev(e[3])
            if op == '/':
                return _idiv(a, b)
            if op == '%':
                return a - _idiv(a, b) * (b or 1)
            if op == '&&':
                return int(bool(a) and bool(b))
            if op == '||':
                return int(bool(a) or bool(b))
            return int({'+': lambda: a + b, '-': lambda: a - b, '*': lambda: a * b,
                        '==': lambda: a == b, '!=': lambda: a != b, '<': lambda: a < b,
                        '<=': lambda: a <= b, '>': lambda: a > b, '>=': lambda: a >= b}[op]())
        if t == 'call':
            n, a = e[1], [self.ev(v) for _, v in e[2]] if e[1] not in ('key.pressed', 'key.down') else None
            if n in ('key.pressed', 'key.down'):
                return int(e[2][0][1][1].upper() in self.keys)
            return {'abs': lambda: abs(a[0]), 'min': lambda: min(a), 'max': lambda: max(a),
                    'clamp': lambda: min(max(a[0], a[1]), a[2]),
                    'sign': lambda: (a[0] > 0) - (a[0] < 0), 'sq': lambda: a[0] * a[0],
                    'sqrt': lambda: int(math.sqrt(a[0])),
                    'dist': lambda: int(math.hypot(a[2] - a[0], a[3] - a[1])),
                    'sin': lambda: esex.SIN_TABLE[((a[0] % 360) + 360) % 360],
                    'cos': lambda: esex.SIN_TABLE[((a[0] + 90) % 360 + 360) % 360]}[n]()
        raise AssertionError(e)

    def __getitem__(self, name):
        return self.env[name]


def run(body, frames=0, **kw):
    """Run top-level statements (init) and optionally `frames` main-loop frames."""
    return Machine(body, **kw).frame(frames)


class Loops(unittest.TestCase):
    def test_for_exclusive(self):
        self.assertEqual(run("let t = 0\nfor i in 0..5 { t += i }")['t'], 10)

    def test_for_inclusive(self):
        self.assertEqual(run("let t = 0\nfor i in 0..=5 { t += i }")['t'], 15)

    def test_for_step(self):
        self.assertEqual(run("let t = 0\nfor i in 0..7 step 2 { t += i }")['t'], 0 + 2 + 4 + 6)

    def test_for_negative_step(self):
        self.assertEqual(run("let t = 0\nfor i in 5..0 step -1 { t += i }")['t'], 15)
        self.assertEqual(run("let t = 0\nfor i in 3..=1 step -1 { t += i }")['t'], 6)

    def test_for_bounds_are_expressions_evaluated_once(self):
        m = run("let n = 3\nlet c = 0\nfor i in 0..n { n += 1\nc++ }")
        self.assertEqual(m['c'], 3)

    def test_repeat(self):
        self.assertEqual(run("let t = 0\nrepeat 4 { t += 3 }")['t'], 12)

    def test_nested_repeat(self):
        self.assertEqual(run("let c = 0\nrepeat 3 { repeat 4 { c++ } }")['c'], 12)

    def test_repeat_count_evaluated_once(self):
        self.assertEqual(run("let n = 3\nlet c = 0\nrepeat n { n += 1\nc++ }")['c'], 3)

    def test_break_and_continue(self):
        m = run("let t = 0\nfor i in 0..100 { if i == 5 { break }\nif i % 2 == 1 { continue }\nt += i }")
        self.assertEqual(m['t'], 0 + 2 + 4)

    def test_continue_runs_the_step(self):        # would loop forever if it skipped i++
        self.assertEqual(run("let c = 0\nfor i in 0..4 { continue }\nc = 1")['c'], 1)

    def test_break_only_leaves_inner_loop(self):
        m = run("let c = 0\nfor a in 0..3 { for b in 0..10 { if b == 2 { break }\nc++ } }")
        self.assertEqual(m['c'], 6)

    def test_while_still_works(self):
        self.assertEqual(run("let i = 0\nwhile i < 7 { i++ }")['i'], 7)

    def test_continue_in_main_loop_skips_rest_of_frame(self):
        m = run("let a = 0\nlet b = 0\nwhile true { a++\nif a > 0 { continue }\nb++ }", frames=3)
        self.assertEqual((m['a'], m['b']), (3, 0))


class Expressions(unittest.TestCase):
    def test_ternary(self):
        self.assertEqual(run("let a = 5\nlet r = a > 3 ? 10 : 20")['r'], 10)
        self.assertEqual(run("let a = 1\nlet r = a > 3 ? 10 : a > 0 ? 30 : 40")['r'], 30)

    def test_word_operators(self):
        m = run("let a = 1\nlet b = 0\nlet r1 = a and b\nlet r2 = a or b\nlet r3 = not b\nlet r4 = not a")
        self.assertEqual((m['r1'], m['r2'], m['r3'], m['r4']), (0, 1, 1, 0))

    def test_inc_dec(self):
        m = run("let a = 5\na++\na++\na--\nlet b = 10 - -3")
        self.assertEqual((m['a'], m['b']), (6, 13))

    def test_new_functions(self):
        m = run("let a = sign(-9)\nlet b = sign(0)\nlet c = sign(4)\nlet d = sq(7)\nlet e = dist(0, 0, 3, 4)")
        self.assertEqual((m['a'], m['b'], m['c'], m['d'], m['e']), (-1, 0, 1, 49, 5))

    def test_time_seconds(self):
        esex.Program("let s = time.s\nlet t = time.sec")        # compiles/scans

    def test_key_names(self):
        for name in ("HOME", "END", "NUM0", "NUM9", "PAGEUP", "A", "F5", "SPACE"):
            esex.key_code(('str', name))
        with self.assertRaises(esex.ESError):
            esex.key_code(('str', 'NUM10'))

    def test_float_literals(self):
        m = run("float pi = 3.14\nfloat a = 8.79\nfloat whole = 5")
        self.assertEqual((m['pi'], m['a'], m['whole']), (3140, 8790, 5000))

    def test_bool_literals(self):
        m = run("let ok = true\nlet nope = false")
        self.assertEqual((m['ok'], m['nope']), (1, 0))

    def test_sin_cos(self):
        m = run("let s0 = sin(0)\nlet s90 = sin(90)\nlet s180 = sin(180)\n"
                "let c0 = cos(0)\nlet c90 = cos(90)\nlet sneg = sin(-90)")
        self.assertEqual((m['s0'], m['s90'], m['s180'], m['c0'], m['c90'], m['sneg']),
                          (0, 1000, 0, 1000, 0, -1000))


class Functions(unittest.TestCase):
    def test_basic_call(self):
        m = run("fn add(a, b) { r = a + b }\nadd(2, 3)")
        self.assertEqual(m['r'], 5)

    def test_arguments_are_evaluated_before_assignment(self):
        m = run("let a = 1\nlet b = 2\nfn f(a, b) { r = a * 10 + b }\nf(b, a)")
        self.assertEqual(m['r'], 21)

    def test_function_calling_function(self):
        m = run("fn inner(x) { r = x * 2 }\nfn outer(y) { inner(y + 1) }\nouter(4)")
        self.assertEqual(m['r'], 10)

    def test_call_without_parens_and_no_params(self):
        m = run("fn bump() { n++ }\nbump()\nbump()")
        self.assertEqual(m['n'], 2)

    def test_defined_after_use(self):
        self.assertEqual(run("go()\nfn go() { z = 9 }")['z'], 9)

    def test_call_in_main_loop(self):
        m = run("fn tick() { t++ }\nwhile true { tick() }", frames=4)
        self.assertEqual(m['t'], 4)

    def test_call_inside_onclick(self):
        p = esex.Program('fn hit() { n++ }\narea(x: 0, y: 0, w: 5, h: 5, onclick: { hit() })')
        self.assertTrue(p.click)

    def test_errors(self):
        for src, msg in [
            ("fn f() { f() }\nf()", "recursion"),
            ("fn f(a) { }\nf(1, 2)", "takes 1 argument"),
            ("fn f() { }\nfn f() { }", "defined twice"),
            ("if 1 { fn g() { } }", "top level"),
            ("fn draw.text() { }", "expected"),
            ("fn beep() { }", "built-in"),
        ]:
            with self.assertRaises(esex.ESError, msg=src) as cm:
                esex.Program(src)
            self.assertIn(msg, str(cm.exception), src)


class Drawing(unittest.TestCase):
    def test_drawing_loop_runs_at_paint_time_only(self):
        p = esex.Program('for i in 0..3 { draw.rect(x: i * 10, y: 0, w: 5, h: 5) }')
        self.assertEqual(len(p.paint), 1)
        self.assertEqual(p.paint[0][0], 'while')
        self.assertEqual(p.init, [])

    def test_mixed_loop_body_keeps_only_drawing_in_paint(self):
        p = esex.Program('let c = 0\nfor i in 0..3 { c++\ndraw.circle(x: i, y: i, r: 2) }')
        loop = p.paint[0]
        self.assertTrue(any(s[0] == 'call' for s in loop[2]))
        self.assertTrue(any(s[0] == 'assign' for s in loop[2]))   # kept: it runs at paint time

    def test_buttons_in_loops_rejected(self):
        with self.assertRaises(esex.ESError):
            esex.Program('for i in 0..3 { button(x: 0, y: 0, w: 5, h: 5, text: "a") }')

    def test_plain_loops_stay_in_update(self):
        p = esex.Program('let t = 0\nfor i in 0..3 { t += i }')
        self.assertTrue(any(s[0] == 'while' for s in p.init))
        self.assertEqual(p.paint, [])

    def test_new_draw_commands_compile(self):
        src = ('window(width: 200, height: 200)\n'
               'draw.clear("#000")\n'
               'draw.ellipse(x: 1, y: 2, w: 30, h: 10, color: "red", outline: "white")\n'
               'draw.bar(x: 0, y: 0, w: 100, h: 10, value: 30, max: 60, color: "green", back: "gray")\n'
               'draw.rect(x: 0, y: 0, w: 9, h: 9, color: "none", outline: "white")\n'
               'draw.text(x: 5, y: 5, text: "hi", align: "right")\n'
               'draw.circle(x: 5, y: 5, r: 4, color: mouse.over(0, 0, 9, 9) ? "red" : "blue")\n')
        self.assertEqual(esex.compile_source(src)[:2], b'MZ')

    def test_bad_align_and_none_colour(self):
        with self.assertRaises(esex.ESError):
            esex.compile_source('draw.text(x: 1, y: 1, text: "a", align: "middle")')
        with self.assertRaises(esex.ESError):
            esex.compile_source('draw.text(x: 1, y: 1, text: "a", color: "none")')

    def test_new_shapes_compile(self):
        src = ('window(width: 200, height: 200)\n'
               'draw.triangle(x1: 10, y1: 10, x2: 100, y2: 10, x3: 50, y3: 100, color: "red")\n'
               'draw.star(x: 50, y: 50, r: 30, r2: 12, points: 5, color: "gold", outline: "white")\n'
               'draw.polygon(x: 150, y: 50, radius: 20, points: 6, color: "none", outline: "cyan")\n')
        self.assertEqual(esex.compile_source(src)[:2], b'MZ')

    def test_shape_points_must_be_constant(self):
        with self.assertRaises(esex.ESError):
            esex.compile_source('let n = 5\ndraw.star(x: 1, y: 1, r: 10, points: n)')
        with self.assertRaises(esex.ESError):
            esex.compile_source('draw.polygon(x: 1, y: 1, radius: 10, points: 2)')
        with self.assertRaises(esex.ESError):
            esex.compile_source('draw.polygon(x: 1, y: 1, radius: 10, points: 21)')


class Diagnostics(unittest.TestCase):
    def check(self, src, *needles):
        with self.assertRaises(esex.ESError) as cm:
            esex.compile_source(src)
        for n in needles:
            self.assertIn(n, str(cm.exception))

    def test_did_you_mean(self):
        self.check('draw.tex(x: 1, y: 1, text: "a")', "unknown command", "draw.text")
        self.check('let a = mouse.xx', "mouse.x")

    def test_break_outside_loop(self):
        self.check('break', "inside a loop")
        self.check('while true { break }', "main loop")
        self.check('continue', "inside a loop")

    def test_error_line_numbers(self):
        with self.assertRaises(esex.ESError) as cm:
            esex.parse_source("let a = 1\nlet b = 2\nfor i 0..3 { }")
        self.assertEqual(cm.exception.line, 3)

    def test_cli_shows_source_line(self):
        path = os.path.join(ROOT, '_tmp_bad.es')
        with open(path, 'w') as f:
            f.write('let a = 1\ndraw.tex(x: 1)\n')
        try:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(esex.main([path]), 1)
            self.assertIn('2 | draw.tex(x: 1)', err.getvalue())
        finally:
            os.remove(path)


class Cli(unittest.TestCase):
    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = esex.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_version_constant(self):
        self.assertEqual(esex.VERSION, "5.6.0")

    def test_dash_v(self):
        self.assertEqual(self.run_main('-v'), (0, 'esex 5.6.0\n', ''))
        self.assertEqual(self.run_main('--version'), (0, 'esex 5.6.0\n', ''))

    def test_help_and_no_args(self):
        self.assertEqual(self.run_main('--help')[0], 0)
        self.assertEqual(self.run_main()[0], 1)

    def test_unknown_option(self):
        code, _, err = self.run_main('--bogus', 'x.es')
        self.assertEqual(code, 1)
        self.assertIn('unknown option', err)

    def test_check_writes_nothing(self):
        ex = os.path.join(ROOT, 'examples', 'cookie.es')
        exe = os.path.join(ROOT, 'examples', 'cookie.exe')
        code, out, _ = self.run_main(ex, '--check')
        self.assertEqual(code, 0)
        self.assertIn('OK', out)
        self.assertFalse(os.path.exists(exe))

    def test_setup_version_matches(self):
        with open(os.path.join(ROOT, 'setup.py'), encoding='utf-8') as f:
            text = f.read()
        self.assertIn('version="5.6.0"', text)


class Examples(unittest.TestCase):
    def test_every_example_compiles_to_a_pe(self):
        files = glob.glob(os.path.join(ROOT, 'examples', '*.es'))
        self.assertGreaterEqual(len(files), 3)
        for path in files:
            with open(path, encoding='utf-8-sig') as f:
                exe = esex.compile_source(f.read())
            self.assertEqual(exe[:2], b'MZ', path)
            pe = int.from_bytes(exe[0x3C:0x40], 'little')
            self.assertEqual(exe[pe:pe + 4], b'PE\0\0', path)
            self.assertEqual(int.from_bytes(exe[pe + 4:pe + 6], 'little'), 0x8664, path)

    def test_cookie_clicker_logic(self):
        with open(os.path.join(ROOT, 'examples', 'cookie.es'), encoding='utf-8-sig') as f:
            src = f.read()
        m = Machine(src, keys={'SPACE'})
        m.frame(9)
        self.assertEqual((m['cookies'], m['clicks']), (9, 9))
        m.keys = {'E'}
        m.frame()                                   # 9 cookies: can't afford 10 yet
        self.assertEqual((m['power'], m['cookies']), (1, 9))
        m.keys = {'SPACE'}
        m.frame()                                   # 10 cookies
        m.keys = {'E'}
        m.frame()
        self.assertEqual((m['power'], m['cookies'], m['upgrade_cost']), (2, 0, 20))


# ----------------------------------------------------------------------------
# Differential test: run the *generated x86-64 machine code* natively (Linux
# only) and compare it with the reference interpreter above.  This checks the
# code generator for loops, break/continue, ternaries, arithmetic, sign(), ...
# ----------------------------------------------------------------------------
def _native_available():
    import platform
    return sys.platform.startswith('linux') and platform.machine() in ('x86_64', 'AMD64')


def native_run(src, frames=0):
    import ctypes
    import mmap
    import struct
    prog = esex.Program(src)
    gen = esex.Gen(prog, (0x1000, 0x2000, 0x3000))
    asm = gen.asm
    gen.mode = 'update'
    asm.label('Init')
    gen.emit_block(prog.init)
    asm.emit(b'\xc3')
    asm.label('Frame')
    gen.loops = [('FrameEnd', None)]
    gen.emit_block(prog.update)
    asm.label('FrameEnd')
    asm.emit(b'\xc3')
    asm.resolve()
    region = mmap.mmap(-1, 0x10000, prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC)
    region[0x1000:0x1000 + len(asm.code)] = bytes(asm.code)
    data = bytes(gen.data.buf)
    region[0x3000:0x3000 + len(data)] = data
    base = ctypes.addressof(ctypes.c_char.from_buffer(region))
    proto = ctypes.CFUNCTYPE(None)
    proto(base + asm.labels['Init'])()
    for _ in range(frames):
        proto(base + asm.labels['Frame'])()
    result = {n: struct.unpack('<q', region[rva:rva + 8])[0] for n, rva in gen.var.items()}
    del prog, gen
    return result


NATIVE_PROGRAMS = [
    ("let t = 0\nfor i in 0..10 { t += i }", 0),
    ("let t = 0\nfor i in 0..=10 step 3 { t += i }", 0),
    ("let t = 0\nfor i in 9..0 step -2 { t = t * 2 + i }", 0),
    ("let c = 0\nrepeat 5 { repeat 3 { c++ } }", 0),
    ("let t = 0\nfor i in 0..100 { if i == 7 { break }\nif i % 2 == 1 { continue }\nt += i }", 0),
    ("let c = 0\nfor a in 0..4 { for b in 0..10 { if b == 3 { break }\nc++ } }", 0),
    ("let n = 3\nlet c = 0\nrepeat n { n += 5\nc++ }", 0),
    ("let a = 7\nlet r = a > 3 ? 10 : 20\nlet q = a < 3 ? 10 : a < 9 ? 30 : 40", 0),
    ("let a = 1\nlet b = 0\nlet r1 = a and b\nlet r2 = a or b\nlet r3 = not b\nlet r4 = not a", 0),
    ("let a = -17\nlet b = 5\nlet d = a / b\nlet m = a % b\nlet e = 17 / -5\nlet z = 4 / 0", 0),
    ("let a = sign(-99)\nlet b = sign(0)\nlet c = sign(1234567)\nlet d = sq(-12)\nlet e = dist(1, 1, 4, 5)\nlet f = dist(0, 0, 10, 10)", 0),
    ("let a = clamp(15, 0, 10)\nlet b = clamp(-3, 0, 10)\nlet c = min(4, 9)\nlet d = max(4, 9)\nlet e = abs(-8)", 0),
    ("fn f(a, b) { r = a * 10 + b }\nlet a = 1\nlet b = 2\nf(b, a)", 0),
    ("fn inner(x) { r = x * 2 }\nfn outer(y) { inner(y + 1) }\nouter(4)", 0),
    ("let a = 0\nlet b = 0\nwhile true { a++\nif a > 1 { continue }\nb++ }", 4),
    ("let t = 0\nfn tick(n) { t += n }\nwhile true { tick(3)\nif t > 10 { t = 0 } }", 7),
    ("let a = 5\na++\na++\na--\na *= 3\na -= 1\na %= 7\nlet big = 3000000000 * 4", 0),
]


@unittest.skipUnless(_native_available(), "needs x86-64 Linux to run generated code natively")
class NativeCodegen(unittest.TestCase):
    def test_generated_code_matches_reference(self):
        for src, frames in NATIVE_PROGRAMS:
            ref = Machine(src).frame(frames)
            got = native_run(src, frames)
            for name, value in got.items():
                self.assertEqual(value, ref[name], "%s  ->  %s (source: %r)" % (name, (value, ref[name]), src))


if __name__ == '__main__':
    unittest.main()
