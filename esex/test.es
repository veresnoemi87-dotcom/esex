// ES Cookie Clicker 🍪

window(
    title: "ES Cookie Clicker",
    width: 900,
    height: 700
)

resizable.enable()

let cookies = 0
let clicks = 0
let upgrade_cost = 10
let power = 1

draw.text(
    x: 30,
    y: 30,
    text: "ES COOKIE CLICKER",
    color: "#ffcc33"
)

draw.text(
    x: 30,
    y: 80,
    text: "Cookies:",
    color: "#ffffff"
)

draw.text(
    x: 30,
    y: 120,
    text: "Click the cookie!",
    color: "#ffffff"
)

button(
    x: 300,
    y: 250,
    w: 300,
    h: 150,
    text: "🍪 CLICK COOKIE 🍪",
    onclick: "cookies = cookies + power"
)

button(
    x: 300,
    y: 430,
    w: 300,
    h: 60,
    text: "Upgrade - 10 cookies",
    onclick: "cookies = cookies - upgrade_cost"
)

while true {
    if key.down("SPACE") {
        cookies = cookies + power
    }

    if key.down("E") {
        power = power + 1
        upgrade_cost = upgrade_cost + 10
    }
}