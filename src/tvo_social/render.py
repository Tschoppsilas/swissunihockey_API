from __future__ import annotations

from pathlib import Path

from .models import TeamGame
from .templates.base import Template


def render_page(
    template: Template,
    categorized_games: dict[str, list[TeamGame]],
    page_idx: int,
    page_count: int,
    title: str,
    out_path: Path,
) -> Path:
    image = template.background()
    image = template.render(image, categorized_games, page_idx, page_count, title)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(out_path)
    return out_path


def render_batches(
    template: Template,
    pages: list[dict[str, list[TeamGame]]],
    out_dir: Path,
    prefix: str,
    title: str,
) -> list[Path]:
    page_count = len(pages)
    paths = []
    for idx, categorized_games in enumerate(pages):
        out_path = out_dir / f"{prefix}_{idx + 1}of{page_count}.png"
        paths.append(render_page(template, categorized_games, idx, page_count, title, out_path))
    return paths
