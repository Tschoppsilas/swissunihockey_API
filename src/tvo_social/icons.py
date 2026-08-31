from __future__ import annotations

from PIL import ImageDraw

# Small hand-drawn icons (no emoji/external assets) so they render
# consistently and match the club's flat red/black/white style at any size.


def draw_clock_icon(
    draw: ImageDraw.ImageDraw, cx: float, cy: float, radius: float, color, width: int = 2
) -> None:
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=color, width=width)
    draw.line([cx, cy, cx, cy - radius * 0.7], fill=color, width=width)  # minute hand
    draw.line([cx, cy, cx + radius * 0.5, cy + radius * 0.15], fill=color, width=width)  # hour hand


def draw_pin_icon(
    draw: ImageDraw.ImageDraw, cx: float, top: float, height: float, color, hole_color
) -> None:
    head_r = height * 0.3
    head_cy = top + head_r
    draw.ellipse(
        [cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r], fill=color
    )
    draw.polygon(
        [
            (cx - head_r * 0.85, head_cy + head_r * 0.35),
            (cx + head_r * 0.85, head_cy + head_r * 0.35),
            (cx, top + height),
        ],
        fill=color,
    )
    hole_r = head_r * 0.42
    draw.ellipse(
        [cx - hole_r, head_cy - hole_r, cx + hole_r, head_cy + hole_r], fill=hole_color
    )
