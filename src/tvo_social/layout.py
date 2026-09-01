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

# Story pages deliberately don't pack anywhere near the full page_capacity()
# above - that's what made a busy weekend look like a wall of cards. Instead,
# pagination is capped much lower (fewer categories per slide, more slides),
# while rendering still fills the *full* page_capacity() - the adaptive
# scaling (MIN_SCALE..MAX_SCALE below) then blows up that smaller amount of
# content to fill the extra room, which is what makes it "bigger and airier"
# rather than just leaving blank space.
STORY_PAGINATION_CAPACITY = 1300  # safety net - the two caps below normally bind first
STORY_SECTION_GAP = 50  # vs. the default 34 - clearer separation between categories

# Pure pixel height doesn't guarantee a consistent "how full does this slide
# feel" - a slide of 4 Junioren-E categories (typically 3 games each) has
# noticeably more content than 4 categories with the usual 2 games each,
# even at a similar height. These two explicit caps make slide fullness
# predictable regardless of composition: whichever is hit first ends the
# slide. 4 categories x ~2 games is the common case; 9 games caps a slide of
# mostly 3-game (E-Junioren) categories to 3 of them instead of 4.
STORY_MAX_CATEGORIES_PER_SLIDE = 4
STORY_MAX_GAMES_PER_SLIDE = 9

# Category badge and (announce-only) venue pill sit side by side on one row.
BANNER_HEIGHT = 46
BANNER_GAP_BELOW = 8  # tight: banner row belongs visually to what follows

CARD_GAP = 10
SECTION_GAP = 34  # looser: separates one category's block from the next

CARD_HEIGHT: dict[str, int] = {"results": 60, "announce": 60}


def category_height(
    num_games: int, kind: Literal["announce", "results"], section_gap: float = SECTION_GAP
) -> float:
    if num_games <= 0:
        return 0.0
    card_height = CARD_HEIGHT[kind]
    header_height = BANNER_HEIGHT + BANNER_GAP_BELOW
    return (
        header_height
        + num_games * card_height
        + (num_games - 1) * CARD_GAP
        + section_gap
    )


# When a page shows only a few categories/games (e.g. a home-tournament-only
# post, or a story page deliberately capped below), scale everything up so
# the content fills the page instead of clumping at the top with empty space
# below. Never shrinks below the baseline size (1.0), and capped so a single
# game doesn't blow up absurdly.
MIN_SCALE = 1.0
MAX_SCALE = 1.4


def total_content_height(
    categorized: dict[str, list],
    kind: Literal["announce", "results"],
    section_gap: float = SECTION_GAP,
) -> float:
    return sum(category_height(len(games), kind, section_gap) for games in categorized.values())


def compute_scale(
    categorized: dict[str, list],
    kind: Literal["announce", "results"],
    profile: CanvasProfile = FEED_PROFILE,
    section_gap: float = SECTION_GAP,
) -> float:
    total = total_content_height(categorized, kind, section_gap)
    if total <= 0:
        return MIN_SCALE
    ideal = profile.page_capacity() / total
    return max(MIN_SCALE, min(MAX_SCALE, ideal))
