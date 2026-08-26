from __future__ import annotations

from PIL import ImageDraw, ImageFont

_FONT_CACHE: dict[tuple[str | None, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}


def load_font(font_path: str | None, size: int):
    key = (font_path, size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    font = None
    if font_path:
        try:
            font = ImageFont.truetype(font_path, size)
        except OSError:
            font = None  # font file not found on this machine, fall back below

    if font is None:
        try:
            font = ImageFont.load_default(size=size)
        except TypeError:
            # Older Pillow: load_default() has no size parameter.
            font = ImageFont.load_default()

    _FONT_CACHE[key] = font
    return font


def fit_line(draw: ImageDraw.ImageDraw, line: str, font, max_width: int) -> str:
    """Truncate a single line with an ellipsis so it never overflows max_width."""
    if draw.textlength(line, font=font) <= max_width:
        return line

    ellipsis = "…"
    for cut in range(len(line) - 1, 0, -1):
        candidate = line[:cut].rstrip() + ellipsis
        if draw.textlength(candidate, font=font) <= max_width:
            return candidate
    return ellipsis
