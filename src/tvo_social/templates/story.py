from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .. import layout
from .base_card import BaseCardTemplate

# Native resolution (941x1672) is scaled up to the story canvas
# (layout.STORY_PROFILE.canvas_size) on load - it's the same ~9:16 aspect
# ratio, just exported smaller, so the resize is effectively lossless.
BACKGROUND_PATH = Path(__file__).parent / "assets" / "Story.png"


class StoryTemplate(BaseCardTemplate):
    """The story post: every game of the weekend, all categories, no home-
    venue filter (that's the feed post's job) - always the announce-style
    time/matchup card, never results."""

    profile = layout.STORY_PROFILE

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("kind", "announce")
        super().__init__(**kwargs)

    def background(self) -> Image.Image:
        image = Image.open(BACKGROUND_PATH).convert("RGB")
        return image.resize(self.profile.canvas_size)

    def _draw_title(
        self,
        draw: ImageDraw.ImageDraw,
        content_start_y: float,
        page_idx: int,
        page_count: int,
        title: str,
    ) -> None:
        header = title
        if page_count > 1:
            header += f" - {page_idx + 1}/{page_count}"
        self._draw_adaptive_title(draw, header, content_start_y, align="left")
