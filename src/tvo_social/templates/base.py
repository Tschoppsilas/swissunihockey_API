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
    ) -> None:
        """Draw everything (banners, cards, header) directly onto image."""
        ...
