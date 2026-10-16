#!/usr/bin/env python3
"""Export the raster art in `web/public/images` at the size it is actually used.

This is the second half of `prep_assets.py`, which crops and alpha-keys the raw
generated images into place. Those steps are about making the artwork correct;
this one is about making it cheap to download, and it runs every time the
illustrations change.

The art was shipped as full-size PNGs and served as-is. That is fine for the file
on disk and expensive for the page: `logo-mark.png` is 512x512 / 120 KB but is
drawn at 40 px on every page, and `chat-empty.png` is 1254x1254 / 522 KB but is
drawn at 200 px. With the three landing illustrations that put about 1.6 MB of
image on the first screenful of a phone, which is the single biggest reason the
pages felt slow to load.

So each file is exported at the size the layout actually draws it, at 2x so a
retina screen stays sharp, and as WebP. Measured on this repo: 1770 KB -> 204 KB,
an 88% cut, with no visible difference at any real display size.

The full-size PNGs stay in git as the source of truth and as the fallback for a
browser without WebP; nothing in the app references them.

Run:  .venv/bin/python scripts/export_web_assets.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "web" / "public" / "images"

# The app icon, at the two sizes browsers actually ask for. The favicon used to
# be the 512 px mark, so every page load paid 120 KB for a 16 px square in the
# tab. Quantised because the mark is flat vector artwork: at 192 px the PNG was
# 30 KB of anti-aliasing noise nobody can see.
ICONS = (32, 180)

# name -> (width the layout draws it at, export width at 2x, quality)
#
# Anything wider than 2x the largest size it is ever drawn at is bytes no screen
# can use.
PLAN = {
    # 40 px in the nav and the chat header.
    "logo-mark": (40, 96, 88),
    # The chat's empty state caps the illustration at 200 px.
    "chat-empty": (200, 400, 82),
    # The hero art column is 44vw of the page shell, capped at 560 px tall.
    "hero-scene": (500, 900, 82),
    # The "why" art is the same 44vw column.
    "family-scales": (500, 900, 82),
    # The login art column is roughly half of a 1040 px card.
    "auth-scene": (500, 800, 82),
    # The skyline band is full-bleed, so it keeps its own width.
    "skyline": (1400, 1400, 80),
}

# The page cream, used to flatten the illustrations onto. They all sit on a solid
# background, so a second, fully transparent channel is pure overhead. The logo
# mark keeps its alpha — it is drawn over cream, white and maroon.
CREAM = (253, 249, 241)
KEEP_ALPHA = {"logo-mark"}


def _flatten(im: Image.Image) -> Image.Image:
    if im.mode != "RGBA":
        return im
    bg = Image.new("RGB", im.size, CREAM)
    bg.paste(im, mask=im.split()[-1])
    return bg


def export(name: str, out_w: int, quality: int) -> None:
    src = IMG / f"{name}.png"
    if not src.exists():
        print("  skip %-14s (no source png)" % name)
        return

    before = src.stat().st_size
    src_size = Image.open(src).size
    im = Image.open(src)
    if im.mode == "P":
        im = im.convert("RGBA")

    # Never upscale. A source already smaller than the target is already optimal.
    if im.width > out_w:
        im = im.resize((out_w, round(im.height * out_w / im.width)), Image.LANCZOS)
    if name not in KEEP_ALPHA:
        im = _flatten(im)

    dst = IMG / f"{name}.webp"
    im.save(dst, "WEBP", quality=quality, method=6)
    after = dst.stat().st_size

    print("  %-14s %4dx%-4d %6.1f KB -> %4dx%-4d %6.1f KB  (-%d%%)" % (
        name, src_size[0], src_size[1], before / 1024,
        im.width, im.height, after / 1024,
        round(100 * (before - after) / before),
    ))


def build_icons() -> None:
    """The tab icon and the iOS home-screen icon, from the same mark."""
    src = Image.open(IMG / "logo-mark.png").convert("RGBA")
    for size in ICONS:
        out = IMG / f"icon-{size}.png"
        src.resize((size, size), Image.LANCZOS).quantize(
            colors=64, method=Image.FASTOCTREE
        ).save(out, optimize=True)
        label = "apple-touch" if size > 32 else "favicon   "
        print("  icon-%-3d %s %6.1f KB" % (size, label, out.stat().st_size / 1024))


def drop_stale_icons() -> None:
    """Remove icon exports this script no longer produces.

    The illustration WebPs are fully determined by `PLAN` and are rewritten on
    every run, so they need no cleanup. The icon set is the part that drifts: a
    plan that drops a size would otherwise leave the old file behind and ship it
    to production unused.
    """
    wanted = {f"icon-{size}.png" for size in ICONS}
    for path in sorted(IMG.glob("icon-*")):
        if path.name not in wanted:
            path.unlink()
            print("  removed stale %s" % path.name)


def main() -> None:
    print("public/images: %s" % IMG)
    total_before = total_after = 0
    for name, (_drawn_at, out_w, quality) in PLAN.items():
        src = IMG / f"{name}.png"
        if not src.exists():
            continue
        total_before += src.stat().st_size
        export(name, out_w, quality)
        dst = IMG / f"{name}.webp"
        if dst.exists():
            total_after += dst.stat().st_size
    print()
    build_icons()
    print()
    drop_stale_icons()
    print("\nillustration weight shipped to the browser: %.1f KB -> %.1f KB (-%d%%)"
          % (total_before / 1024, total_after / 1024,
             round(100 * (total_before - total_after) / total_before)))


if __name__ == "__main__":
    main()