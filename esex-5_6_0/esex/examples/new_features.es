window(title: "New features", width: 600, height: 500, background: "#101820")

float pi = 3.14
let spinning = true
let angle = 0

draw.text(x: 20, y: 20, text: "pi*1000 = {pi}", color: "white")
draw.text(x: 20, y: 50, text: "sin(30)={sin(30)} cos(60)={cos(60)}", color: "white")

draw.triangle(x1: 50, y1: 400, x2: 150, y2: 400, x3: 100, y3: 300, color: "orange")
draw.polygon(x: 300, y: 350, radius: 50, points: 6, color: "cyan", outline: "white")

for i in 0..3 {
    draw.star(x: 450 + i * 0, y: 150 + i * 100, r: 35, r2: 15, points: 5, color: "gold", outline: "white")
}

while true {
    if spinning {
        angle = (angle + 1) % 360
    }
    if key.pressed("SPACE") { spinning = not spinning }
}
