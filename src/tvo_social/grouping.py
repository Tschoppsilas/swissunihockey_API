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
