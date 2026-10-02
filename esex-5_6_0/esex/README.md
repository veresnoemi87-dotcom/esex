# ESEX 5.5

**ESEX** compiles **ES (Executable Script)** programs straight to native Windows x64 `.exe` files.

There is no C compiler, linker or runtime involved: ESEX writes the machine code and the PE file itself, in a single Python file (`esex.py`). The resulting programs are small (10–20 KB), start instantly and only use the Windows libraries that are always there (`user32`, `gdi32`, `kernel32`).

```
esex game.es              ->  game.exe
esex game.es -o out.exe
esex -v                   ->  esex 5.5.0
```

ES is a small language for 2D windows: text, shapes, buttons, keyboard and mouse input, a main loop. It is meant for games, toys and little tools.

---

## Contents

1. [Install](#install)
2. [Command line](#command-line)
3. [A first program](#a-first-program)
4. [How a program runs](#how-a-program-runs)
5. [Language reference](#language-reference)
6. [Drawing and UI reference](#drawing-and-ui-reference)
7. [Input, built-in values and functions](#input-built-in-values-and-functions)
8. [Errors and warnings](#errors-and-warnings)
9. [Limits](#limits)
10. [Upgrading to 5.5](#upgrading-to-55)
11. [Examples and tests](#examples-and-tests)
12. [Changelog](#changelog)

---

## Install

You need Python 3.7 or newer. The compiler runs anywhere Python does, but the `.exe` files it produces run on **Windows x64**.

```
pip install .            # from this folder;  add -e for an editable install
esex -v                  # -> esex 5.5.0
```

You can also skip installing and run it directly: `python esex.py game.es`.

## Command line

```
esex <source.es> [-o output.exe] [--check] [--run]
```

| Option | Meaning |
|---|---|
| `-o FILE` | Name of the `.exe` to write. Default: the source name with `.exe`. |
| `--check`, `-c` | Only check the script for errors. Writes nothing. |
| `--run`, `-r` | Start the program after compiling (Windows only). |
| `-v`, `--version` | Print the version (`esex 5.5.0`) and exit. |
| `-h`, `--help` | Show usage. |

The exit code is `0` on success and `1` on any error. Errors show the line number and the offending source line.

## A first program

```
window(title: "Hello", width: 400, height: 300, background: "#1b1b2f")

let clicks = 0

draw.text(x: 20, y: 20, text: "Clicked {clicks} times", color: "white", size: 24)

button(
    x: 100, y: 120, w: 200, h: 60,
    text: "Click me",
    onclick: { clicks++ }
)
```

Save it as `hello.es`, run `esex hello.es --run`.

## How a program runs

- **Drawing commands describe what the window looks like.** `draw.*` and `button` calls are re-drawn on every frame, so `"Score: {score}"` is always up to date. You never "redraw" by hand.
- **Everything else runs once per frame in the main loop** `while true { ... }`, 60 times per second by default (`fps` option of `window`). There can be only one main loop.
- **Statements before the main loop** run once, at start-up.
- **`onclick` code runs once** when the left mouse button goes down on that button or area.
- Drawing happens in source order: earlier commands are underneath later ones.
- A `draw.*` call inside an `if` is drawn only while the condition is true.

## Language reference

### Comments, statements, literals

```
// line comment
/* block comment */
let a = 1; let b = 2        // ';' or a newline ends a statement
```

- All numbers are **64-bit integers** (`42`, `-7`, `0xFF`). `/` truncates toward zero, and dividing by zero is safe (it divides by 1).
- `true` is `1`, `false` is `0`. Any non-zero value counts as true. `let ok = true` / `let ok = false` work directly.
- `float name = value` declares a variable that stores `value` scaled by 1000 (fixed-point), e.g. `float pi = 3.14` stores `3140`. Arithmetic on it is ordinary integer arithmetic on the scaled value — divide by `1000` when you need the unscaled result (`pi / 1000` is `3`). `sin`/`cos` return values on the same ×1000 scale, so floats and trig compose directly.
- Strings (`"..."` or `'...'`) exist only as text for drawing, `alert(...)`, `title(...)` and colours. They are not values you can store in variables.
- Inside a string, `{expression}` is replaced by its number: `"HP: {hp} / {max_hp}"`, `"{score * 2}"`. Use `\{` and `\}` for literal braces, and `\n`, `\t`, `\"`, `\\`.

### Variables

```
let score = 0          // let, var and const all mean the same thing
score = score + 1
score += 5             // also -=  *=  /=  %=
score++                // also --
```

All variables are global 64-bit integers. A variable that is read but never assigned stays `0` (ESEX prints a warning).

### Operators

From lowest to highest precedence:

| | Operators |
|---|---|
| ternary | `cond ? a : b` |
| or | `\|\|`  `or` |
| and | `&&`  `and` |
| equality | `==`  `!=` |
| comparison | `<`  `<=`  `>`  `>=` |
| add | `+`  `-` |
| multiply | `*`  `/`  `%` |
| unary | `-x`  `!x`  `not x` |

Comparisons and logic give `1` or `0`. Use parentheses freely.

### Conditions and loops

```
if hp <= 0 {
    alert("Game over")
} else if hp < 20 {
    beep()
} else {
    score++
}

while x < 100 { x += 3 }

for i in 0..10 { total += i }          // 0 .. 9   (end is excluded)
for i in 0..=10 { total += i }         // 0 .. 10  (..= includes the end)
for i in 0..100 step 25 { ... }        // 0, 25, 50, 75
for i in 10..0 step -1 { ... }         // 10 .. 1  (counts down)

repeat 5 { lives++ }                   // run the body 5 times

break        // leave the innermost loop
continue     // jump to the next iteration
```

- The bounds of `for` and the count of `repeat` are evaluated **once**, before the loop starts.
- In the **main loop**, `continue` skips the rest of the current frame. `break` is not allowed there; call `exit()` to quit.
- A loop that contains `draw.*` commands is a *drawing loop*: it runs **at paint time**, not in the update step. See [Drawing loops](#drawing-loops).

### Functions (`fn`)

```
fn add_score(points) {
    score += points
    if score > best { best = score }
}

add_score(10)
```

- Functions are defined at the top level, before or after their first use.
- They are **inlined** at every call, so they can contain anything a normal block can: drawing, buttons, loops, other function calls, and they work inside `onclick`.
- Arguments are numbers (expressions). All arguments are evaluated before any parameter is assigned, so calling `f(b, a)` on a function `fn f(a, b)` behaves as you expect.
- Parameters are ordinary global variables. Give them names that do not clash with your other variables.
- Functions have no return value and cannot call themselves (recursion is rejected with an error).

```
fn hud(px, py, value) {
    draw.text(x: px, y: py, text: "HP {value}", color: "white")
}
hud(20, 20, hp)
```

### Reserved words

`let var const if else while loop for in step repeat break continue fn and or not true false`

## Drawing and UI reference

Arguments can be named (`x: 10`) or positional in the order shown. Numbers can be any expression.

### Window

```
window(title: "My game", width: 900, height: 700, fps: 60, background: "#101820", resizable: 1)
resizable.enable()          // resizable.disable()
title("Now playing")        // change the title from the running program
```

`window(...)` values must be constants. `bg` is a short name for `background`.

### Colours

Wherever a `color` is expected you can write:

- `"#rgb"` or `"#rrggbb"`: `"#fc3"`, `"#ffcc33"`
- a name: `black white red green blue yellow cyan magenta orange purple pink brown gray grey gold lime navy teal silver darkgray lightgray`
- `rgb(r, g, b)` with each part `0..255`, so it can be computed
- `cond ? "red" : "#333"` to pick between colours
- `"none"` (or `"transparent"`) as the fill of a shape, to draw only its `outline`

### Drawing commands

| Command | Options (in order) | Notes |
|---|---|---|
| `draw.text` | `x y text color size bold align` | `size` default 20, `bold: 1`, `align: "left" \| "center" \| "right"` (x is the anchor). |
| `draw.rect` | `x y w h color outline` | Top-left corner + size. |
| `draw.roundrect` | `x y w h color radius outline` | `radius` default 16. |
| `draw.circle` | `x y r color outline` | `x, y` is the **centre**. |
| `draw.ellipse` | `x y w h color outline` | Fits the box `x, y, w, h`. |
| `draw.line` | `x1 y1 x2 y2 color width` | |
| `draw.bar` | `x y w h value max color back` | Progress / health bar. `max` default 100, `value` is clamped to `0..max`. |
| `draw.clear` | `color` | Fills the whole window. |
| `draw.triangle` | `x1 y1 x2 y2 x3 y3 color outline` | Three points, filled (or hollow with `color: "none"`). |
| `draw.polygon` | `x y points radius color outline` | A regular polygon centred at `x, y`. `points` (3–20) must be a constant. |
| `draw.star` | `x y r r2 points color outline` | A star centred at `x, y`; `r` is the outer radius, `r2` the inner radius (default `r / 2`). `points` (3–20) must be a constant. |

Aliases: `add.text`, `draw.rectangle`, `draw.rrect`, `new.window`. Option aliases: `width`→`w`, `height`→`h`, `radius`→`r` (for circles), `colour`→`color`.

Text uses the Segoe UI font. GDI cannot draw colour emoji reliably, so draw pictures with shapes instead.

### Buttons and click areas

```
button(x: 300, y: 450, w: 300, h: 60, text: "Upgrade: {cost}", color: "#2e8b57",
       onclick: { if cookies >= cost { cookies -= cost } })

area(x: 340, y: 190, w: 220, h: 220, onclick: { cookies += power })   // invisible
```

- `button` draws a rounded button with hover and pressed shading. Options: `x y w h text onclick color size`.
- `area` is the same click region without any drawing. Use it over shapes you drew yourself.
- `onclick` is a `{ block }` (or a string of statements). It cannot contain `draw.*` or `button`.
- `button` and `area` cannot be placed inside loops.

### Drawing loops

A loop that contains `draw.*` commands runs when the window is painted:

```
for row in 0..8 {
    for col in 0..8 {
        draw.rect(x: col * 80, y: row * 80, w: 80, h: 80,
                  color: (row + col) % 2 == 0 ? "#f0d9b5" : "#b58863")
    }
}
```

Because the whole loop runs at paint time, other statements inside it (for example `count++`) also run at every paint. Use dedicated loop variables and keep game logic in the main loop.

## Input, built-in values and functions

### Keyboard

```
key.down("SPACE")       // true while held (only while the window has focus)
key.pressed("SPACE")    // true once per key press
```

Key names: `A`..`Z`, `0`..`9`, `F1`..`F12`, `NUM0`..`NUM9`, `SPACE ENTER RETURN ESC ESCAPE LEFT UP RIGHT DOWN SHIFT CTRL ALT TAB BACKSPACE DELETE HOME END PAGEUP PAGEDOWN INSERT MINUS PLUS COMMA PERIOD WIN`, and `MOUSE LMOUSE RMOUSE`.

Use `key.pressed` for one-shot actions (buying, firing, pausing) and `key.down` for movement.

### Mouse

| Name | Meaning |
|---|---|
| `mouse.x`, `mouse.y` | Cursor position in the window (`mouse_x`, `mouse_y` also work). |
| `mouse.down` | Left button is held. |
| `mouse.right` | Right button is held. |
| `mouse.clicked` | `1` in the frame the left button went down. |
| `mouse.over(x, y, w, h)` | Cursor is inside that rectangle. |

### Values

| Name | Meaning |
|---|---|
| `window.w`, `window.h` | Current client size (`window.width`, `window.height` also work). |
| `frame` | Frame counter. |
| `time.ms` | Milliseconds since Windows started. |
| `time.s` | The same in seconds (`time.sec` also works). |

These are read-only.

### Functions

| Function | Result |
|---|---|
| `abs(x)` `sign(x)` `sq(x)` | Absolute value, `-1/0/1`, `x * x`. |
| `min(a, b)` `max(a, b)` `clamp(v, lo, hi)` | |
| `sqrt(x)` | Integer square root (truncated). |
| `dist(x1, y1, x2, y2)` | Integer distance between two points. |
| `sin(deg)` `cos(deg)` | Sine/cosine of a degree angle, scaled ×1000 (`sin(90)` is `1000`). Table-based, any integer degree (including negative). |
| `random(lo, hi)` | Random integer from `lo` to `hi`, both included (`math.random` is the same). |
| `rgb(r, g, b)` | A colour value. |
| `key.down(k)` `key.pressed(k)` `mouse.over(x, y, w, h)` | See above. |

### Actions

| Statement | Effect |
|---|---|
| `exit()` | Close the program. |
| `beep()` | System beep (`sound.beep()` also works). |
| `alert("text {x}")` | Message box. |
| `title("text {x}")` | Change the window title. |

## Errors and warnings

Errors stop the compile and point at the line:

```
game.es: error: unknown command 'draw.tex' (did you mean 'draw.text'?)
     7 | draw.tex(x: 20, y: 20, text: "Hi")
```

`esex game.es --check` reports errors without writing an `.exe`. Warnings (for example a variable that is used but never assigned) go to stderr and do not stop the compile.

## Limits

- Integers only (floats are fixed-point, scaled ×1000); no arrays or string variables.
- `points` on `draw.polygon` and `draw.star` must be a constant from 3 to 20 (the point list is built at compile time).
- Windows x64 executables only. The compiler itself is portable Python.
- Text per `draw.text` / `alert` is limited to about 500 characters (each `{number}` counts as up to 21).
- One main loop. `while true` anywhere else is an error.
- Functions are inlined, so they cannot recurse.
- `break` cannot be used directly in the main loop.

## Upgrading to 5.5

Programs written for 5.0 compile to the same executable as before, apart from the changes below:

- `and`, `or`, `not`, `fn`, `for`, `repeat`, `break`, `continue` and `in` are now reserved words. Rename variables that used them.
- `--` and `++` are now operators, so `a--b` no longer means `a - (-b)`. Write `a - -b`.
- `draw.text` with a `align` other than `"left"`, `"center"` or `"right"` is now an error (before it was ignored).
- Loops that contain `draw.*` commands are now allowed (they used to be an error) and run at paint time.

## Examples and tests

`examples/` contains:

| File | Shows |
|---|---|
| `cookie.es` | A clicker game: `fn`, `area`, `button`, `draw.bar`, `key.pressed`. |
| `features.es` | A tour of the 5.5 features: bouncing ball, `for`, `continue`, ternary colours, `dist`, `sign`, `draw.ellipse`, right-aligned text, `mouse.over`. |
| `checkerboard.es` | Nested drawing loops, a hollow outline (`color: "none"`), click and arrow-key selection. |
| `new_features.es` | `float`, booleans, `sin`/`cos`, `draw.triangle`, `draw.polygon`, `draw.star`. |

Compile one: `esex examples/cookie.es --run`.

Run the test-suite (no Windows needed):

```
python -m unittest discover tests -v
```

It checks the language semantics with a reference interpreter, that every example compiles to a valid PE, the command line, and (on x86-64 Linux) it executes the generated machine code and compares the results with the interpreter.

## Changelog

### 5.6.0
- **Language:** `float name = value` (fixed-point, scaled ×1000); `let name = true/false` booleans (already worked via `true`/`false` folding to `1`/`0`, now documented).
- **Values and functions:** `sin(deg)`, `cos(deg)` (degree-based, table-driven, scaled ×1000 to match floats).
- **Drawing:** `draw.triangle`, `draw.polygon`, `draw.star`.

### 5.5.0
- **Language:** `for i in a..b [step s]` (and `a..=b`), `repeat n`, `break`, `continue`, `fn` user functions, ternary `c ? a : b`, `and` / `or` / `not`, `++` / `--`.
- **Drawing:** `draw.ellipse`, `draw.bar`, `draw.clear`, `align: "right"`, hollow shapes with `color: "none"`, colour choice with a ternary of strings, and loops that contain `draw.*` commands.
- **Values and functions:** `sign`, `sq`, `dist`, `mouse.over`, `mouse.right`, `time.s`, more key names (`HOME`, `END`, `PAGEUP`, `PAGEDOWN`, `INSERT`, `NUM0`..`NUM9`, ...).
- **Tool:** `esex -v` / `--version`, `--check`, `--run`, errors show the source line, "did you mean" hints.
- Added this README, examples and a test-suite. Requires Python 3.7+.

### 5.0.0
- Native PE compiler with a built-in assembler: windows, drawing commands, buttons, keyboard and mouse input.
