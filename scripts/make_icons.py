#!/usr/bin/env python3
"""Generate the xy-graph-gen PWA icon set (static/icons/*.png).

Draws everything with Pillow at 4x supersampling and downscales with LANCZOS,
so the strokes stay clean at the small sizes a launcher uses.

Two looks:
  * "any" icons  — light card, faint grid, slate axes, blue sine curve
                   (the same visual language as the inline SVG favicon).
  * "maskable"   — full-bleed accent blue with a white glyph inside the 80%
                   safe zone, so Android's circular/squircle crop looks
                   deliberate instead of clipping the drawing.

The thick curve is STAMPED (a circle of radius width/2 at every sample) rather
than drawn with `ImageDraw.line(joint="curve")`, which leaves a visibly furry
edge on a path this curved.

Usage:  python3 scripts/make_icons.py           # writes static/icons/
Requires Pillow (system python3 has it; the app venv does not need it).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

SS = 4  # supersample factor
SAMPLES = 900  # curve samples per icon (stamping needs density, not speed)

# Palette — kept in lockstep with the app's light theme (:root in index.html).
BG = "#f8fafc"
GRID = "#dbe3ec"
AXIS = "#94a3b8"
CURVE = "#2563eb"
MASK_BG = "#2563eb"
MASK_FG = "#ffffff"
MASK_GRID = (255, 255, 255, 46)  # faint white grid on the blue maskable tile


def rgb(value: str | tuple, alpha: int = 255) -> tuple[int, int, int, int]:
    if isinstance(value, tuple):
        return value
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha)


def stamp_path(d: ImageDraw.ImageDraw, pts: list[tuple[float, float]], width: float,
               fill) -> None:
    """Draw a smooth round-capped/round-joined stroke by stamping discs."""
    r = width / 2
    box = (r, r)
    for x, y in pts:
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def draw_glyph(
    d: ImageDraw.ImageDraw,
    size: int,
    *,
    bg,
    grid,
    axis: str,
    curve,
    inset: float,
    stroke: float,
    with_grid: bool = True,
    axis_frac: float = 0.016,
) -> None:
    """Draw grid + axes + one sine period into a size x size canvas.

    `inset` is the fraction of the canvas left blank on each side before the
    plot box is drawn; `stroke` is the curve width as a fraction of size.
    """
    d.rectangle([0, 0, size, size], fill=rgb(bg))

    x0 = y0 = size * inset
    x1 = y1 = size * (1 - inset)
    w = x1 - x0
    h = y1 - y0
    cy = size / 2

    if with_grid and grid is not None:
        step = w / 8
        lw = max(1, round(size * 0.006))
        for i in range(9):
            x = x0 + i * step
            y = y0 + i * (h / 8)
            d.line([x, y0, x, y1], fill=rgb(grid), width=lw)
            d.line([x0, y, x1, y], fill=rgb(grid), width=lw)

    # Axes: solid, slightly heavier, arrowhead at the right/top ends.
    aw = max(2, round(size * axis_frac))
    head = w * 0.05
    d.line([x0, cy, x1 - aw, cy], fill=rgb(axis), width=aw)
    d.line([size / 2, y1, size / 2, y0 + aw], fill=rgb(axis), width=aw)
    d.polygon([(x1, cy), (x1 - head, cy - head * 0.45), (x1 - head, cy + head * 0.45)], fill=rgb(axis))
    d.polygon([(size / 2, y0), (size / 2 - head * 0.45, y0 + head), (size / 2 + head * 0.45, y0 + head)], fill=rgb(axis))

    # One full sine period, kept fully inside the plot box (the stroke's own
    # radius is subtracted from the domain so the round caps stay in bounds).
    cw = max(3, round(size * stroke))
    pad = cw / 2
    ax0, ax1 = x0 + pad, x1 - pad
    amp = (h / 2 - pad) * 0.86
    span = ax1 - ax0
    pts = []
    for i in range(SAMPLES + 1):
        t = i / SAMPLES
        pts.append((ax0 + t * span, cy - amp * math.sin(t * 2 * math.pi)))
    stamp_path(d, pts, cw, rgb(curve))


def make(name: str, size: int, *, maskable: bool = False, with_grid: bool = True,
         axis_frac: float = 0.016) -> Path:
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if maskable:
        # Full-bleed tile; glyph lives inside the 80% safe zone.
        draw_glyph(d, s, bg=MASK_BG, grid=MASK_GRID, axis=MASK_FG,
                   curve=MASK_FG, inset=0.22, stroke=0.072)
    else:
        draw_glyph(d, s, bg=BG, grid=GRID, axis=AXIS, curve=CURVE,
                   inset=0.12, stroke=0.062, with_grid=with_grid,
                   axis_frac=axis_frac)
    img = img.resize((size, size), Image.LANCZOS)
    out_dir = Path(__file__).resolve().parent.parent / "static" / "icons"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    img.save(path, "PNG", optimize=True)
    print(f"{path.relative_to(out_dir.parent.parent)}  {size}x{size}  {path.stat().st_size} bytes")
    return path


def main() -> int:
    make("icon-192.png", 192)
    make("icon-512.png", 512)
    make("icon-maskable-192.png", 192, maskable=True)
    make("icon-maskable-512.png", 512, maskable=True)
    make("apple-touch-icon-180.png", 180)
    make("favicon-32.png", 32, with_grid=False, axis_frac=0.05)  # grid turns to mush at 32px
    return 0


if __name__ == "__main__":
    sys.exit(main())
