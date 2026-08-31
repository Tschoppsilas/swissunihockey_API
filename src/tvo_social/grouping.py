from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from . import layout
from .models import Game, TeamGame

# Rough age/seniority ordering for section sorting within a post. Matched as a
# case-insensitive substring against each category's display label; anything
# unmatched sorts alphabetically after all known categories.
CATEGORY_PRIORITY = [
    "Herren",
    "Damen",
    "U18",
    "U16",
    "U14",
    "Junioren C",
    "Junioren D",
    "Junioren E",
    "Junioren F",
]


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


def dedupe_games(games: list[Game]) -> list[Game]:
    """Remove duplicate games (same game can appear twice when both
    the home and away team are TVO teams, since games are fetched
    per-team)."""
    seen: set[int] = set()
    unique: list[Game] = []
    for game in games:
        if game.id in seen:
            continue
        seen.add(game.id)
        unique.append(game)
    return unique


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


def _category_sort_key(label: str) -> tuple[int, str]:
    lower = label.lower()
    for index, keyword in enumerate(CATEGORY_PRIORITY):
        if keyword.lower() in lower:
            return (index, label)
    return (len(CATEGORY_PRIORITY), label)


def group_by_category(team_games: list[TeamGame]) -> dict[str, list[TeamGame]]:
    """Group one week's games by display category, in a sensible section order
    (Herren/Damen first, then Junioren oldest to youngest), games within a
    category sorted chronologically."""
    grouped: dict[str, list[TeamGame]] = {}
    for tg in team_games:
        grouped.setdefault(tg.category, []).append(tg)
    for games in grouped.values():
        games.sort(key=lambda tg: (tg.date, tg.game.time or ""))
    return dict(sorted(grouped.items(), key=lambda kv: _category_sort_key(kv[0])))


def paginate_by_category(
    categorized: dict[str, list[TeamGame]],
    kind: Literal["announce", "results"],
    profile: layout.CanvasProfile = layout.FEED_PROFILE,
    capacity: float | None = None,
) -> list[dict[str, list[TeamGame]]]:
    """Split categorized games into pages (one dict per output image),
    keeping every category's games together on a single page. A category
    that alone exceeds the capacity still gets its own (overfull) page
    rather than being split mid-category.

    Capacity defaults to the actual pixel height available on one image of
    the given canvas profile (see layout.py), so pagination always matches
    what the template renders - pass an explicit capacity only for testing.
    """
    if capacity is None:
        capacity = profile.page_capacity()

    pages: list[dict[str, list[TeamGame]]] = []
    current: dict[str, list[TeamGame]] = {}
    current_height = 0.0

    for category, games in categorized.items():
        height = layout.category_height(len(games), kind)
        if current and current_height + height > capacity:
            pages.append(current)
            current = {}
            current_height = 0.0
        current[category] = games
        current_height += height

    if current:
        pages.append(current)

    return pages
