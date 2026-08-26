from __future__ import annotations

from typing import Literal

# Shared geometry constants: grouping.py uses these to decide how many
# categories fit on one page, templates/instagram_v1.py uses the exact same
# numbers to actually draw the page. Keeping a single source of truth means
# pagination decisions always match what gets rendered.

CANVAS_SIZE = (1080, 1350)

CONTENT_TOP = 300
CONTENT_BOTTOM = 1300  # safe margin above the canvas edge

BANNER_HEIGHT = 50
BANNER_GAP_BELOW = 16
CARD_GAP = 14
SECTION_GAP = 30

CARD_HEIGHT: dict[str, int] = {"results": 64, "announce": 84}


def category_height(num_games: int, kind: Literal["announce", "results"]) -> float:
    if num_games <= 0:
        return 0.0
    card_height = CARD_HEIGHT[kind]
    return (
        BANNER_HEIGHT
        + BANNER_GAP_BELOW
        + num_games * card_height
        + (num_games - 1) * CARD_GAP
        + SECTION_GAP
    )


def page_capacity() -> float:
    return CONTENT_BOTTOM - CONTENT_TOP
