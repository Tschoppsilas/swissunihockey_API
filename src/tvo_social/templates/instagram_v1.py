from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .. import layout
from ..fonts import fit_line, load_font
from .base_card import CONTENT_X, CONTENT_WIDTH, FONT_BOLD, HEADER_Y, TVO_RED, BaseCardTemplate

BACKGROUND_PATH = Path(__file__).parent / "assets" / "background_v1.png"

# Fixed title for the home-tournament feed post (kind="announce"); the
# date-based, left-aligned "GAME WEEKEND - ..." title belongs to the story
# post (see templates/story.py) instead.
HOME_TOURNAMENT_TITLE = "HEIMSPIEL"


class InstagramV1Template(BaseCardTemplate):
    """The feed post: home-tournament-only announcements (kind="announce",
    filtered to the club's home venue in cli.py) or weekly results
    (kind="results")."""

    profile = layout.FEED_PROFILE

    def background(self) -> Image.Image:
        return Image.open(BACKGROUND_PATH).convert("RGB")

    def _draw_title(
        self,
        draw: ImageDraw.ImageDraw,
        content_start_y: float,
        page_idx: int,
        page_count: int,
        title: str,
    ) -> None:
        if self.kind == "announce":
            self._draw_adaptive_title(draw, HOME_TOURNAMENT_TITLE, content_start_y, align="center")
        else:
            header = title
            if page_count > 1:
                header += f" - {page_idx + 1}/{page_count}"
            header_font = load_font(FONT_BOLD, 34)
            draw.text(
                (CONTENT_X, HEADER_Y),
                fit_line(draw, header, header_font, CONTENT_WIDTH),
                font=header_font,
                fill=TVO_RED,
            )
