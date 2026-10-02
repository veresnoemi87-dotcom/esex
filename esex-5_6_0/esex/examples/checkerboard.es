// Checkerboard: nested drawing loops + a clickable board that remembers the cell.

window(title: "Checkerboard", width: 640, height: 680, background: "#202020")

let size = 80
let sel_col = 3
let sel_row = 3

for row in 0..8 {
    for col in 0..8 {
        draw.rect(
            x: col * size, y: row * size, w: size, h: size,
            color: (row + col) % 2 == 0 ? rgb(240, 217, 181) : rgb(181, 136, 99)
        )
    }
}

// hover highlight and the selected cell
draw.rect(x: mouse.x / size * size, y: mouse.y / size * size, w: size, h: size, color: "none", outline: "#ffffff")
draw.circle(x: sel_col * size + 40, y: sel_row * size + 40, r: 28, color: "#c0392b", outline: "#7b241c")

draw.text(x: 320, y: 645, text: "Selected: column {sel_col + 1}, row {sel_row + 1}", color: "#ffffff", size: 20, align: "center")

area(
    x: 0, y: 0, w: 640, h: 640,
    onclick: {
        sel_col = mouse.x / size
        sel_row = mouse.y / size
    }
)

while true {
    if key.pressed("LEFT") and sel_col > 0 { sel_col-- }
    if key.pressed("RIGHT") and sel_col < 7 { sel_col++ }
    if key.pressed("UP") and sel_row > 0 { sel_row-- }
    if key.pressed("DOWN") and sel_row < 7 { sel_row++ }
}
