from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from . import layout
from .models import TeamGame


def week_bounds(d: date) -> tuple[date, date]:
    """Return (Monday, Sunday) of the Mon-Sun week containing d."""
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def week_key(d: date) -> str:
    """ISO week key, e.g. '2026-W36', used for output folder names."""
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def last_completed_week(today: date) -> tuple[date, date]:
    """The most recently finished Mon-Sun window as of `today`.

    On a Sunday, that day's games are already over by evening, so the
    current week counts as completed (this is what makes the Sunday-
    evening automation pick up the week that just ended). On any other
    day, the previous full week is the last completed one.
    """
    monday, sunday = week_bounds(today)
    if today.weekday() == 6:  # Sunday
        return monday, sunday
    return monday - timedelta(days=7), monday - timedelta(days=1)


def half_season_end(today: date) -> date:
    """Next Swiss-unihockey schedule cutoff: 30.06. or 31.12.

    Some categories only have a schedule up to December, after which
    groups are re-split and rescheduled - looking further ahead than
    the next cutoff would be incomplete/wrong for those teams.
    """
    if today.month <= 6:
        return date(today.year, 6, 30)
    return date(today.year, 12, 31)


def format_date_range(dates: list[date]) -> str:
    """Format a set of dates as a single day ('20.09.') or a range
    ('19.-20.09.' same month, '28.09.-04.10.' across months)."""
    lo, hi = min(dates), max(dates)
    if lo == hi:
        return f"{lo:%d.%m.}"
    if lo.month == hi.month:
        return f"{lo:%d.}-{hi:%d.%m.}"
    return f"{lo:%d.%m.}-{hi:%d.%m.}"


def format_weekend_title(team_games: list[TeamGame], label: str) -> str:
    """e.g. 'GAME WEEKEND - 20.09.' from the actual game dates, rather than
    an ISO week number - games are always on a weekend, so the calendar
    week label doesn't carry information the reader needs."""
    return f"{label} - {format_date_range([tg.date for tg in team_games])}"


def group_games_by_week(team_games: list[TeamGame]) -> dict[str, list[TeamGame]]:
    """Group games by ISO week, sorted chronologically within and across weeks."""
    ordered = sorted(team_games, key=lambda tg: (tg.date, tg.game.time or ""))
    grouped: dict[str, list[TeamGame]] = {}
    for tg in ordered:
        key = week_key(tg.date)
        grouped.setdefault(key, []).append(tg)
    return grouped


def group_by_category(team_games: list[TeamGame]) -> dict[str, list[TeamGame]]:
    """Group one week's games by display category, sections ordered by each
    category's own earliest game (date, then time) - whichever team plays
    first shows first, rather than a fixed seniority order. Games within a
    category are sorted chronologically."""
    grouped: dict[str, list[TeamGame]] = {}
    for tg in team_games:
        grouped.setdefault(tg.category, []).append(tg)
    for games in grouped.values():
        games.sort(key=lambda tg: (tg.date, tg.game.time or ""))
    return dict(
        sorted(grouped.items(), key=lambda kv: (kv[1][0].date, kv[1][0].game.time or "", kv[0]))
    )


def _pack_pages(
    items: list[tuple[str, list[TeamGame], float]],
    capacity: float,
    max_categories: int | None,
    max_games: int | None,
    page_targets: list[int] | None = None,
) -> list[dict[str, list[TeamGame]]] | None:
    """Fill pages left to right, never splitting a category. With no
    page_targets, each page is packed as full as the hard limits allow
    (plain greedy). With page_targets (one category-count target per
    intended page), a page also closes once it reaches its own target -
    used to spread categories evenly across a known number of pages rather
    than always maxing out early pages. Returns None if page_targets can't
    be honored (packing needed more pages than were targeted), so the
    caller can fall back to the plain greedy result."""
    pages: list[dict[str, list[TeamGame]]] = []
    current: dict[str, list[TeamGame]] = {}
    current_height = 0.0
    current_games = 0

    for category, games, height in items:
        page_index = len(pages)
        target = page_targets[page_index] if page_targets and page_index < len(page_targets) else None

        exceeds_height = current_height + height > capacity
        exceeds_categories = max_categories is not None and len(current) + 1 > max_categories
        exceeds_games = max_games is not None and current_games + len(games) > max_games
        exceeds_target = target is not None and len(current) + 1 > target

        if current and (exceeds_height or exceeds_categories or exceeds_games or exceeds_target):
            pages.append(current)
            current = {}
            current_height = 0.0
            current_games = 0

        current[category] = games
        current_height += height
        current_games += len(games)

    if current:
        pages.append(current)

    if page_targets is not None and len(pages) > len(page_targets):
        return None

    return pages


def paginate_by_category(
    categorized: dict[str, list[TeamGame]],
    kind: Literal["announce", "results"],
    profile: layout.CanvasProfile = layout.FEED_PROFILE,
    capacity: float | None = None,
    section_gap: float = layout.SECTION_GAP,
    max_categories: int | None = None,
    max_games: int | None = None,
) -> list[dict[str, list[TeamGame]]]:
    """Split categorized games into pages (one dict per output image),
    keeping every category's games together on a single page. A category
    that alone exceeds any limit still gets its own (overfull) page rather
    than being split mid-category.

    A new page starts as soon as adding the next category would exceed
    *any* of: the pixel height capacity, max_categories, or max_games -
    whichever binds first. Capacity defaults to the actual pixel height
    available on one image of the given canvas profile (see layout.py), so
    pagination always matches what the template renders; max_categories/
    max_games (both unset by default) are optional additional caps so a
    page's "fullness" stays predictable regardless of composition - e.g. a
    category with 3 games (Junioren E) counts for more than one with 2,
    which pixel height alone approximates but doesn't guarantee.

    When either cap is set, pagination is balanced: first a plain greedy
    pack determines the minimum number of pages needed, then categories are
    redistributed as evenly as possible across exactly that many pages
    (e.g. 7 categories over 2 pages -> 4+3, not 4+2+1 over 3 pages worth of
    greedy fill followed by a nearly-empty last page) - falling back to the
    plain greedy result if an even split isn't actually feasible within
    that page count.
    """
    if capacity is None:
        capacity = profile.page_capacity()

    items = [
        (category, games, layout.category_height(len(games), kind, section_gap))
        for category, games in categorized.items()
    ]

    pages = _pack_pages(items, capacity, max_categories, max_games)

    if (max_categories is not None or max_games is not None) and len(pages) > 1:
        page_targets = _even_split_targets(len(items), len(pages))
        balanced = _pack_pages(items, capacity, max_categories, max_games, page_targets)
        if balanced is not None:
            pages = balanced

    return pages


def _even_split_targets(total_items: int, num_pages: int) -> list[int]:
    """Category-count target per page so `total_items` split across
    `num_pages` pages as evenly as possible, any remainder going to the
    earliest pages (e.g. 7 over 2 -> [4, 3], 8 over 3 -> [3, 3, 2])."""
    base, remainder = divmod(total_items, num_pages)
    return [base + 1 if i < remainder else base for i in range(num_pages)]
