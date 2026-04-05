"""
Creates a macOS-style squircle app icon from icon.jpg.
- 1024x1024 canvas
- Blue/indigo gradient background
- Squircle (rounded rect) mask with ~22% corner radius
- Icon centered with padding
"""
from PIL import Image, ImageDraw, ImageFilter
import math, os

SIZE = 1024
RADIUS = int(SIZE * 0.225)   # ~22% corner radius — matches macOS squircle

src = os.path.join(os.path.dirname(__file__), '..', 'icon.jpg')
out = os.path.join(os.path.dirname(__file__), 'icon_rounded.png')

# --- background gradient (dark blue → indigo) ---
bg = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
for y in range(SIZE):
    t = y / SIZE
    r = int(30  + t * (79  - 30))
    g = int(58  + t * (70  - 58))
    b = int(138 + t * (229 - 138))
    for x in range(SIZE):
        bg.putpixel((x, y), (r, g, b, 255))

# --- squircle mask ---
mask = Image.new('L', (SIZE, SIZE), 0)
draw = ImageDraw.Draw(mask)
draw.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=RADIUS, fill=255)

# --- apply mask to background ---
bg.putalpha(mask)

# --- load & prep the icon ---
icon = Image.open(src).convert('RGBA')
icon_size = int(SIZE * 0.72)
icon = icon.resize((icon_size, icon_size), Image.LANCZOS)

# Black lines on white bg → white lines on transparent bg
# Use darkness of each pixel as its alpha, then paint it white
r, g, b, a = icon.split()
# darkness = how far from white; use as alpha
darkness = r.point(lambda p: 255 - p)
white = Image.new('RGBA', icon.size, (255, 255, 255, 255))
white.putalpha(darkness)
icon = white

# --- composite icon centered on background ---
canvas = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
canvas.paste(bg, (0, 0), bg)
offset = (SIZE - icon_size) // 2
canvas.paste(icon, (offset, offset), icon)

canvas.save(out, 'PNG')
print(f"Saved {out}")
