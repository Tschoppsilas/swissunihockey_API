from __future__ import annotations

import sys

from PIL import ImageDraw, ImageFont

_FONT_CACHE: dict[tuple[str | None, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
_LOGGED_PATHS: set[str | None] = set()


def _log_once(font_path: str | None, message: str) -> None:
    # Once per distinct font path (not per size/call) so a font used at ten
    # sizes doesn't spam the log - printed straight to stderr rather than via
    # `logging` so it always shows up, including in the webapp's captured
    # subprocess output, with no logging configuration required.
    if font_path in _LOGGED_PATHS:
        return
    _LOGGED_PATHS.add(font_path)
    print(f"[fonts] {message}", file=sys.stderr)


def load_font(font_path: str | None, size: int):
    key = (font_path, size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]

    font = None
    if font_path:
        try:
            font = ImageFont.truetype(font_path, size)
            _log_once(font_path, f"geladen: {font_path}")
        except OSError as exc:
            # Font file not found/unreadable on this machine - fall back
            # below to Pillow's built-in bitmap font (no bold, limited
            # Unicode coverage), which is exactly the silent-fallback bug
            # this log line exists to catch immediately instead of only
            # noticing missing umlauts in the rendered image.
            _log_once(
                font_path,
                f"FEHLER beim Laden von '{font_path}' ({exc}) "
                "- falle auf Pillow-Standardschrift zurueck (kein Fett, eingeschraenkter Zeichensatz)",
            )
            font = None

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
