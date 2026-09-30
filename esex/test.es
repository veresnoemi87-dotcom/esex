// ES Cookie Clicker

window(
    title: "ES Cookie Clicker",
    width: 900,
    height: 700,
    background: "#1b1b2f"
)

resizable.enable()

let cookies = 0
let clicks = 0
let upgrade_cost = 10
let power = 1

// ---- HUD ----
draw.text(x: 30, y: 25, text: "ES COOKIE CLICKER", color: "#ffcc33", size: 32, bold: 1)
draw.text(x: 30, y: 80, text: "Cookies: {cookies}", color: "#ffffff", size: 28)
draw.text(x: 30, y: 120, text: "Per click: {power}    Clicks: {clicks}", color: "#bbbbbb", size: 20)
draw.text(x: 30, y: 155, text: "Click the cookie or press SPACE. Press E to upgrade.", color: "#888888", size: 16)

// ---- the cookie (drawn, since GDI can't render emoji reliably) ----
draw.circle(x: 450, y: 300, r: 110, color: "#c68642", outline: "#8a5a2b")
draw.circle(x: 410, y: 265, r: 14, color: "#4a2c17")
draw.circle(x: 490, y: 280, r: 14, color: "#4a2c17")
draw.circle(x: 440, y: 335, r: 14, color: "#4a2c17")
draw.circle(x: 505, y: 345, r: 12, color: "#4a2c17")
draw.circle(x: 385, y: 320, r: 11, color: "#4a2c17")

// clickable area over the cookie
area(
    x: 340,
    y: 190,
    w: 220,
    h: 220,
    onclick: {
        cookies = cookies + power
        clicks = clicks + 1
    }
)

// ---- upgrade button ----
button(
    x: 300,
    y: 450,
    w: 300,
    h: 60,
    text: "Upgrade: {upgrade_cost} cookies",
    color: "#2e8b57",
    onclick: {
        if cookies >= upgrade_cost {
            cookies = cookies - upgrade_cost
            power = power + 1
            upgrade_cost = upgrade_cost + 10
        }
    }
)

// ---- keyboard (key.pressed = once per key press, not every frame) ----
while true {
    if key.pressed("SPACE") {
        cookies = cookies + power
        clicks = clicks + 1
    }

    if key.pressed("E") {
        if cookies >= upgrade_cost {
            cookies = cookies - upgrade_cost
            power = power + 1
            upgrade_cost = upgrade_cost + 10
        }
    }
}
