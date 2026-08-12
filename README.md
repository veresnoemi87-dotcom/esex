# ES — Executable Script

**A tiny scripting language that compiles directly into native Windows executables.**

ES is a lightweight DSL designed to make simple Windows programs feel ridiculously easy to write.

You write an `.es` file.
`esex` compiles it.
You get a real `.exe`.

No interpreter bundled with your program. No Python runtime required. No giant framework hiding underneath it.

Just **ES → native x64 PE executable**.

---

## ✨ What is ES?

ES (**Executable Script**) is a small, Python-powered compiler project with a very different goal from typical scripting languages.

Instead of running your script through an interpreter, ES turns the script into **native x86-64 machine code** and packages it as a Windows **PE32+ executable**.

That means this:

```es
window(title: "My ES App", width: 800, height: 600)

let x = 400
let y = 300

add.text(text: "Hello from ES!")

draw.circle(
    x: x,
    y: y,
    r: 35,
    color: "#ff3366"
)

while true {
    if key.pressed("W") {
        y = y - 5
    }

    if key.pressed("S") {
        y = y + 5
    }

    if key.pressed("A") {
        x = x - 5
    }

    if key.pressed("D") {
        x = x + 5
    }
}
```

can become a standalone Windows executable.

And yes, the compiler is actually generating the PE file itself.

---

## 🚀 Why ES?

ES isn't trying to replace Python, C++, Rust, or whatever language happens to be winning the internet this week.

It's a **small experimental language** built around one particularly fun idea:

> **What if a simple script could become a native executable without needing a runtime?**

The result is a compact language with things like:

* 🪟 Native Windows windows
* 🎨 Basic GDI rendering
* 🔴 Circles
* 🟩 Rectangles
* 📝 Text rendering
* ⌨️ Keyboard input
* 🔁 Game-style update loops
* 🎨 Hexadecimal colors
* ⚙️ Native x64 machine code generation
* 📦 PE32+ executable generation

---

## 🛠️ Installation

Clone the repository and install ES with pip:

```bash
pip install .
```

After installation, the `esex` command becomes available.

Check the compiler:

```bash
esex --help
```

---

## 📦 Compiling an ES program

Create a file such as `hello.es`:

```es
window(title: "Hello ES", width: 800, height: 600)

add.text(text: "Hello from Executable Script!")
```

Then compile it:

```bash
esex hello.es -o hello.exe
```

You'll get:

```text
hello.exe
```

Run it normally on Windows.

The generated executable does **not** need the ES compiler or Python installed to run.

---

## 🎮 A tiny example

Here's a simple controllable circle:

```es
window(title: "ES Demo", width: 800, height: 600)

let x = 400
let y = 300

draw.circle(x: x, y: y, r: 35, color: "#ff3366")

while true {
    if key.pressed("W") {
        y = y - 5
    }

    if key.pressed("S") {
        y = y + 5
    }

    if key.pressed("A") {
        x = x - 5
    }

    if key.pressed("D") {
        x = x + 5
    }
}
```

WASD moves the circle around the window.

It's simple, but that's kind of the point.

---

## 🧠 How it works

The compiler is written in Python, but the programs it produces are **native Windows executables**.

The rough pipeline looks like this:

```text
       .es source
           │
           ▼
      ES DSL Parser
           │
           ▼
     Python AST / IR
           │
           ▼
     x86-64 Assembler
           │
           ▼
      PE32+ Builder
           │
           ▼
        .exe file
           │
           ▼
       Windows
```

The compiler constructs the executable directly, including things such as:

* DOS header
* PE header
* x64 machine code
* Section headers
* Import directory
* Import Address Table
* `.text`
* `.rdata`
* `.data`

The generated program communicates directly with Windows APIs such as **USER32**, **GDI32**, and **KERNEL32**.

---

## 🎨 Drawing

### Circle

```es
draw.circle(
    x: x,
    y: y,
    r: 30,
    color: "#ff0000"
)
```

### Rectangle

```es
draw.rectangle(
    x: 100,
    y: 100,
    w: 200,
    h: 100,
    color: "#33ccff"
)
```

### Text

```es
add.text(text: "Hello!")
```

Colors can be specified using hexadecimal values:

```es
color: "#ff3366"
```

Basic color names are also supported.

---

## ⌨️ Keyboard input

Keyboard checks can be placed inside a loop:

```es
while true {
    if key.pressed("W") {
        y = y - 5
    }
}
```

The compiler turns these checks into native calls to Windows' keyboard input API.

---

## 🪟 Windows

Create a window with:

```es
window(
    title: "My Program",
    width: 800,
    height: 600
)
```

You can also enable resizing:

```es
resizable.enable()
```

---

## 📖 Compiler options

```text
esex <input.es> [-o output.exe]
```

### Help

```bash
esex --help
```

### Demo code

```bash
esex --help-code
```

### Choose the output filename

```bash
esex game.es -o game.exe
```

---

## 🧪 Project status

ES is an experimental language and compiler project.

It's not trying to be the next C++.

It's trying to be **fun to build, fun to experiment with, and surprisingly capable for something this small**.

The compiler is currently focused on Windows x64 and native PE generation.

Expect the language to evolve as new features are added.

---

## 📁 Project structure

The project is intentionally small:

```text
esex/
├── esex.py
├── setup.py
└── README.md
```

`esex.py` contains the parser, assembler, PE builder, and compiler.

---

## 🔥 The idea

There are plenty of languages that can make an executable.

ES is interested in the part underneath that abstraction.

**How little code can you write before you're basically building the executable yourself?**

That's what this project explores.

```text
ES source
   ↓
machine code
   ↓
PE
   ↓
Windows executable
```

No magic button hiding the interesting part.

Just a tiny language, a compiler, and a whole lot of x86-64 bytes.

---

## 📜 License

See the repository for the current license and project terms.
