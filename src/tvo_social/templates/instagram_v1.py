from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .. import layout
from .base_card import BaseCardTemplate

BACKGROUND_PATH = Path(__file__).parent / "assets" / "background_v1.png"

# Fixed titles for the home-tournament feed posts: the date-based, left-aligned
# "GAME WEEKEND - ..." / "RESULTATE - ..." titles belong to the story posts
# (see templates/story.py) instead.
HOME_TOURNAMENT_TITLE = "HEIMSPIEL"
HOME_RESULTS_TITLE = "RESULTATE"


class InstagramV1Template(BaseCardTemplate):
    """The feed post: home-tournament-only announcements (kind="announce",
    filtered to the club's home venue in cli.py) or the results of those
    home games (kind="results"). Both get a big centered, adaptively sized
    title; pages of a multi-image post repeat it unchanged."""

    profile = layout.FEED_PROFILE

    def __init__(self, results_title: str = HOME_RESULTS_TITLE, **kwargs) -> None:
        super().__init__(**kwargs)
        self.results_title = results_title

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
        text = HOME_TOURNAMENT_TITLE if self.kind == "announce" else self.results_title
        self._draw_adaptive_title(draw, text, content_start_y, align="center")
