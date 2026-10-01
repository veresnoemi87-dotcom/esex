// ES Cookie Clicker (with click animation)

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

// Cookie animation: ES has no decimals, so the scale is a percentage (100 = normal size)
let cookie_scale = 100

fn click_cookie() {
    cookies += power
    clicks++
    cookie_scale = 85
}

fn buy_upgrade() {
    if cookies >= upgrade_cost {
        cookies -= upgrade_cost
        power++
        upgrade_cost += 10
    }
}

draw.text(x: 30, y: 25, text: "ES COOKIE CLICKER", color: "#ffcc33", size: 32, bold: 1)
draw.text(x: 30, y: 80, text: "Cookies: {cookies}", color: "#ffffff", size: 28)
draw.text(x: 30, y: 120, text: "Per click: {power}    Clicks: {clicks}", color: "#bbbbbb", size: 20)
draw.text(x: 30, y: 155, text: "Click the cookie or press SPACE. Press E to upgrade.", color: "#888888", size: 16)

// Cookie (radii are scaled by cookie_scale / 100)
draw.circle(x: 450, y: 300, r: 110 * cookie_scale / 100, color: "#c68642", outline: "#8a5a2b")
draw.circle(x: 410, y: 265, r: 14 * cookie_scale / 100, color: "#4a2c17")
draw.circle(x: 490, y: 280, r: 14 * cookie_scale / 100, color: "#4a2c17")
draw.circle(x: 440, y: 335, r: 14 * cookie_scale / 100, color: "#4a2c17")
draw.circle(x: 505, y: 345, r: 12 * cookie_scale / 100, color: "#4a2c17")
draw.circle(x: 385, y: 320, r: 11 * cookie_scale / 100, color: "#4a2c17")

// Cookie click area
area(x: 340, y: 190, w: 220, h: 220, onclick: { click_cookie() })

// Upgrade button
button(
    x: 300,
    y: 450,
    w: 300,
    h: 60,
    text: "Upgrade: {upgrade_cost} cookies",
    color: "#2e8b57",
    onclick: { buy_upgrade() }
)

// Game loop
while true {
    // Return cookie to normal size
    cookie_scale = min(100, cookie_scale + 3)

    if key.pressed("SPACE") { click_cookie() }
    if key.pressed("E") { buy_upgrade() }
}
