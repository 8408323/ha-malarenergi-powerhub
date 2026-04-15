"""Generate icon.png for the Mälarenergi PowerHub integration.

Design:
  - 256×256 with a circular mask
  - Dark blue background  (#1a3460 — Mälarenergi brand)
  - Water-wave strip at bottom  (semi-transparent lighter blue)
  - Lightning bolt in Python yellow (#FFD43B) with Python blue outline (#3776AB)
  - Small hub-ring (concentric circles) radiating from the bolt tip
"""

from __future__ import annotations

import math
import os
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256
OUT = Path(__file__).parent.parent / "icon.png"

# ── colour palette ──────────────────────────────────────────────────────────
BG          = (26,  52,  96)      # Mälarenergi dark blue
WAVE_FILL   = (40,  90, 160, 80)  # translucent mid-blue wave
BOLT_FILL   = (255, 212,  59)     # Python yellow
BOLT_EDGE   = (55, 118, 171)      # Python blue
HUB_RING    = (255, 212,  59, 160)  # semi-transparent yellow rings


def circle_mask(size: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse((0, 0, size - 1, size - 1), fill=255)
    return mask


def draw_wave(draw: ImageDraw.ImageDraw, y_mid: float, amplitude: float, color: tuple) -> None:
    """Draw a smooth sine-wave filled stripe."""
    pts: list[tuple[float, float]] = []
    for x in range(SIZE + 1):
        y = y_mid + amplitude * math.sin(2 * math.pi * x / SIZE * 2.2 + 0.6)
        pts.append((x, y))
    # close the polygon at the bottom
    pts += [(SIZE, SIZE), (0, SIZE)]
    draw.polygon(pts, fill=color)


def bolt_polygon(cx: float, cy: float, w: float, h: float) -> list[tuple[float, float]]:
    """Classic lightning-bolt polygon centred on (cx, cy)."""
    # normalised coords, then scale
    raw = [
        ( 0.10,  0.00),   # top-right of upper arm
        (-0.30,  0.00),   # top-left  of upper arm
        ( 0.05,  0.45),   # inner notch top
        (-0.15,  0.45),   # inner notch top-left
        ( 0.30,  1.00),   # bottom tip
        (-0.05,  0.55),   # inner notch bottom
        ( 0.18,  0.55),   # inner notch bottom-right
    ]
    return [(cx + p[0] * w, cy + (p[1] - 0.5) * h) for p in raw]


def draw_hub_rings(draw: ImageDraw.ImageDraw, cx: float, cy: float) -> None:
    """Three concentric semi-transparent rings radiating outward."""
    for r, alpha in [(30, 140), (50, 90), (70, 45)]:
        col = (255, 212, 59, alpha)
        draw.ellipse(
            (cx - r, cy - r, cx + r, cy + r),
            outline=col,
            width=3,
        )


# ── compose ─────────────────────────────────────────────────────────────────
img = Image.new("RGBA", (SIZE, SIZE), (*BG, 255))
draw = ImageDraw.Draw(img, "RGBA")

# water wave
draw_wave(draw, y_mid=SIZE * 0.72, amplitude=10, color=WAVE_FILL)

# lightning bolt — centred in the icon
bx, by = SIZE * 0.52, SIZE * 0.48
bw, bh = SIZE * 0.40, SIZE * 0.58
poly = bolt_polygon(bx, by, bw, bh)

# hub rings centred on the icon centre (bolt passes through)
draw_hub_rings(draw, SIZE * 0.52, SIZE * 0.50)

# blue shadow/outline (offset + slightly larger)
shadow = [(x + 4, y + 4) for x, y in poly]
draw.polygon(shadow, fill=(*BOLT_EDGE, 200))

# yellow bolt on top
draw.polygon(poly, fill=BOLT_FILL)
draw.line(poly + [poly[0]], fill=BOLT_EDGE, width=2)

# circular crop
mask = circle_mask(SIZE)
result = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
result.paste(img, mask=mask)

# also save a square version (some HA contexts want no transparency)
final = Image.new("RGBA", (SIZE, SIZE), (*BG, 255))
final.paste(result, mask=result.split()[3])
final.save(OUT, "PNG")

print(f"Saved {OUT}  ({os.path.getsize(OUT)} bytes)")
