// ESEX 5.5 feature tour: a bouncing ball plus every new language feature.
//   P = pause     SPACE = score a point     R = reset     right mouse = teleport ball

window(title: "ESEX 5.5 tour", width: 800, height: 600, background: "#101820")

let x = 400
let y = 300
let vx = 4
let vy = 3
let score = 0
let paused = false

// sum of the odd numbers 1..10, using for + continue
let odd_total = 0
for k in 1..=10 {
    if k % 2 == 0 { continue }
    odd_total += k
}

// user function: inlined wherever it's called
fn glow(gx, gy, gr) {
    draw.circle(x: gx, y: gy, r: gr, color: "#26404f")
    draw.circle(x: gx, y: gy, r: gr / 2, color: "#88ccff")
}

// a loop that draws runs at paint time: background grid
for gx in 0..=8 {
    draw.line(x1: gx * 100, y1: 0, x2: gx * 100, y2: 600, color: "#1c2b38")
}
for gy in 0..=6 {
    draw.line(x1: 0, y1: gy * 100, x2: 800, y2: gy * 100, color: "#1c2b38")
}

// the ball: ternary colours, dist() for hover
draw.circle(
    x: x, y: y, r: 22,
    color: dist(mouse.x, mouse.y, x, y) < 40 ? rgb(255, 210, 90) : (paused ? rgb(255, 90, 90) : rgb(90, 220, 130))
)
glow(60, 540, 26)
glow(740, 540, 26)

// a hover-aware "button" drawn by hand
draw.roundrect(x: 20, y: 20, w: 130, h: 34, color: mouse.over(20, 20, 130, 34) ? rgb(70, 110, 160) : rgb(40, 70, 110), radius: 10)
draw.text(x: 85, y: 26, text: "hover me", color: "#ffffff", size: 18, align: "center")

draw.text(x: 780, y: 20, text: "Score: {score}", color: "#ffffff", size: 24, align: "right")
draw.text(x: 780, y: 52, text: "Speed: {abs(vx) + abs(vy)}   dir: {sign(vx)},{sign(vy)}", color: "#8899aa", size: 16, align: "right")
draw.text(x: 20, y: 70, text: "Odd total: {odd_total}   Uptime: {time.s}s", color: "#8899aa", size: 16)
draw.ellipse(x: 300, y: 540, w: 200, h: 40, color: "#1e2f3c", outline: "#3a5a70")
draw.bar(x: 320, y: 553, w: 160, h: 14, value: score, max: 20, color: "#33cc66", back: "#0d151c")

while true {
    if key.pressed("P") { paused = not paused }
    if key.pressed("SPACE") { score++ }
    if key.pressed("R") {
        score = 0
        x = 400
        y = 300
    }
    if mouse.right { x = mouse.x; y = mouse.y }

    if not paused {
        x += vx
        y += vy
        if x < 22 or x > 778 { vx = -vx }
        if y < 22 or y > 578 { vy = -vy }
    }
}
