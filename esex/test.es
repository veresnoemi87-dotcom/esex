// Configure window and initial state
window(title="DSL Loop & WASD Engine", width=800, height=600)
resizable.enable()

add.text(text="Fully controlled via DSL loop and WASD commands!")

let x = 400
let y = 300
let w = 5
let h = 5

// Game loop defined directly in the DSL
while true:
    if key.pressed("W"):
        y = y - 6
    if key.pressed("S"):
        y = y + 6
    if key.pressed("A"):
        x = x - 6
    if key.pressed("D"):
        x = x + 6

    draw.rect(x, y, w, h, color="red")