from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Shared geometry constants: grouping.py uses these to decide how many
# categories fit on one page, templates use the exact same numbers to
# actually draw the page. Keeping a single source of truth means pagination
# decisions always match what gets rendered.
#
# Horizontal geometry (content width/margins) is identical across templates
# - both the feed post and the story are 1080px wide. Only the available
# vertical space differs, which is what CanvasProfile captures.


@dataclass(frozen=True)
class CanvasProfile:
    name: str
    canvas_size: tuple[int, int]
    content_top: float
    content_bottom: float  # safe margin above the canvas edge

    def page_capacity(self) -> float:
        return self.content_bottom - self.content_top


FEED_PROFILE = CanvasProfile(
    name="feed", canvas_size=(1080, 1350), content_top=300, content_bottom=1300
)
STORY_PROFILE = CanvasProfile(
    name="story", canvas_size=(1080, 1920), content_top=300, content_bottom=1850
)

# Category badge and (announce-only) venue pill sit side by side on one row.
BANNER_HEIGHT = 46
BANNER_GAP_BELOW = 8  # tight: banner row belongs visually to what follows

CARD_GAP = 10
SECTION_GAP = 34  # looser: separates one category's block from the next

CARD_HEIGHT: dict[str, int] = {"results": 60, "announce": 60}


def category_height(num_games: int, kind: Literal["announce", "results"]) -> float:
    if num_games <= 0:
        return 0.0
    card_height = CARD_HEIGHT[kind]
    header_height = BANNER_HEIGHT + BANNER_GAP_BELOW
    return (
        header_height
        + num_games * card_height
        + (num_games - 1) * CARD_GAP
        + SECTION_GAP
    )


# When a page shows only a few categories/games (e.g. a home-tournament-only
# post), scale everything up so the content fills the page instead of
# clumping at the top with empty space below. Never shrinks below the
# baseline size (1.0), and capped so a single game doesn't blow up absurdly.
MIN_SCALE = 1.0
MAX_SCALE = 1.4


def total_content_height(
    categorized: dict[str, list], kind: Literal["announce", "results"]
) -> float:
    return sum(category_height(len(games), kind) for games in categorized.values())


def compute_scale(
    categorized: dict[str, list],
    kind: Literal["announce", "results"],
    profile: CanvasProfile = FEED_PROFILE,
) -> float:
    total = total_content_height(categorized, kind)
    if total <= 0:
        return MIN_SCALE
    ideal = profile.page_capacity() / total
    return max(MIN_SCALE, min(MAX_SCALE, ideal))
