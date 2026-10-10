"""Crop the three.js render to a padded square and build icon/logo PNGs (light + dark text)."""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

raw, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
im = Image.open(raw).convert("RGBA")
box = im.getchannel("A").point(lambda a: 255 if a > 10 else 0).getbbox()
im = im.crop(box)
side = int(max(im.size) * 1.06)
sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
sq.alpha_composite(im, ((side - im.width) // 2, (side - im.height) // 2))
for name, px in (("icon.png", 256), ("icon@2x.png", 512)):
    sq.resize((px, px), Image.LANCZOS).save(out / name)


def logo(h, rgb):
    ic = sq.resize((h, h), Image.LANCZOS)
    f = ImageFont.truetype(FONT, int(h * 0.40))
    tw = int(ImageDraw.Draw(Image.new("RGBA", (1, 1))).textlength("PowerHub", font=f))
    gap = int(h * 0.10)
    im = Image.new("RGBA", (h + gap + tw + int(h * 0.04), h), (0, 0, 0, 0))
    im.alpha_composite(ic, (0, 0))
    ImageDraw.Draw(im).text((h + gap, h // 2), "PowerHub", font=f, fill=rgb, anchor="lm")
    return im


for s, sfx in ((128, ""), (256, "@2x")):
    logo(s, (31, 41, 55)).save(out / f"logo{sfx}.png")
    logo(s, (241, 245, 249)).save(out / f"dark_logo{sfx}.png")
