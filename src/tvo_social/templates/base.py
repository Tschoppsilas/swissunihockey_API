from __future__ import annotations

from typing import Protocol

from PIL import Image

from ..models import TeamGame


class Template(Protocol):
    canvas_size: tuple[int, int]

    def background(self) -> Image.Image:
        ...

    def render(
        self,
        image: Image.Image,
        categorized_games: dict[str, list[TeamGame]],
        page_idx: int,
        page_count: int,
        title: str,
    ) -> Image.Image:
        """Draw everything (banners, cards, header) and return the final
        image (may be a different mode/object than the input, e.g. if the
        template needs RGBA for translucent elements)."""
        ...
