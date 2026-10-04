#!/usr/bin/env python3
"""Turn raw ChatGPT output into web-ready assets.

Two jobs:

* `slot`  — crop a generated image to the exact aspect ratio of the slot it
  fills, so nothing is stretched and nothing needs object-fit hacks in CSS.
* `alpha` — key the near-white studio background out of the logo mark so it sits
  on cream, maroon or white without a visible box.

Both then quantise. These are flat vector-style images, so a 64-colour palette
is visually free and takes a 1.4 MB PNG down to ~120 KB.

    python3 scripts/prep_assets.py slot  raw in out 16 9
    python3 scripts/prep_assets.py alpha raw in out
"""
import sys

from PIL import Image

PALETTE_COLORS = 64


def slot(src: str, dst: str, num: int = 16, den: int = 9) -> None:
    """Centre-crop to the slot's aspect ratio, then resize to a sane width."""
    im = Image.open(src).convert("RGB")
    w, h = im.size
    want = num / den
    have = w / h
    if have > want:  # too wide, trim the sides
        new_w = int(round(h * want))
        left = (w - new_w) // 2
        im = im.crop((left, 0, left + new_w, h))
    else:  # too tall, trim top and bottom (art usually sits low, so bias down)
        new_h = int(round(w / want))
        top = int(round((h - new_h) * 0.35))
        im = im.crop((0, top, w, top + new_h))
    target_w = 1400 if num >= den else 1000
    if im.width > target_w:
        im = im.resize(
            (target_w, max(1, int(round(target_w / (num / den))))), Image.LANCZOS
        )
    im.quantize(colors=PALETTE_COLORS, method=Image.MEDIANCUT, dither=0).save(
        dst, optimize=True
    )
    print(f"slot {dst} {im.size[0]}x{im.size[1]} ratio {num}:{den}")


def alpha(src: str, dst: str, size: int = 512) -> None:
    """Turn a near-white background transparent and trim the empty margin."""
    im = Image.open(src).convert("RGBA")
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, _ = px[x, y]
            # Distance from white, scaled so cream backgrounds also clear out.
            d = max(0, 255 - min(r, g, b))
            if d < 14:
                px[x, y] = (r, g, b, 0)
            elif d < 40:
                px[x, y] = (r, g, b, int((d - 14) / 26 * 255))
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    side = max(im.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
    square = square.resize((size, size), Image.LANCZOS)
    square.save(dst, optimize=True)
    print(f"alpha {dst} {square.size} trimmed from bbox {bbox}")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    mode = argv[1]
    if mode == "slot":
        _, _, src, dst, num, den = argv
        slot(src, dst, int(num), int(den))
    elif mode == "alpha":
        _, _, src, dst = argv
        alpha(src, dst)
    else:
        print(f"unknown mode {mode}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))