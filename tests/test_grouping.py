from datetime import date

import pytest

from tvo_social import layout
from tvo_social.grouping import (
    group_by_category,
    group_games_by_week,
    half_season_end,
    last_completed_week,
    paginate_by_category,
    week_bounds,
    week_key,
)
from tvo_social.models import Game, TeamGame


def make_game(id: int, d: date, time: str = "18:00", category: str = "Kategorie") -> Game:
    return Game(
        id=id,
        date=d,
        time=time,
        home_team="A",
        away_team="B",
        home_team_id=1,
        away_team_id=2,
        venue="Halle",
        league_text=category,
        category_text=category,
        played=False,
        goals_home=None,
        goals_away=None,
    )


def make_team_game(id: int, d: date, time: str = "18:00", category: str = "Kategorie") -> TeamGame:
    game = make_game(id, d, time, category)
    return TeamGame(
        game=game,
        category=category,
        opponent="B",
        our_goals=None,
        opp_goals=None,
        is_home=True,
    )


def test_week_bounds_mid_week():
    monday, sunday = week_bounds(date(2026, 9, 16))  # Wednesday
    assert monday == date(2026, 9, 14)
    assert sunday == date(2026, 9, 20)


def test_week_bounds_monday_and_sunday():
    assert week_bounds(date(2026, 9, 14)) == (date(2026, 9, 14), date(2026, 9, 20))
    assert week_bounds(date(2026, 9, 20)) == (date(2026, 9, 14), date(2026, 9, 20))


def test_week_key_format():
    assert week_key(date(2026, 9, 16)) == "2026-W38"


@pytest.mark.parametrize(
    "today,expected",
    [
        (date(2026, 3, 15), date(2026, 6, 30)),   # March -> end of June
        (date(2026, 6, 30), date(2026, 6, 30)),   # cutoff day itself -> still June
        (date(2026, 7, 1), date(2026, 12, 31)),   # July -> end of December
        (date(2026, 12, 31), date(2026, 12, 31)),
        (date(2026, 1, 1), date(2026, 6, 30)),
    ],
)
def test_half_season_end(today, expected):
    assert half_season_end(today) == expected


def test_last_completed_week_mid_week():
    # Wednesday 2026-09-16 -> last completed week is the one before (Mon 07 - Sun 13)
    start, end = last_completed_week(date(2026, 9, 16))
    assert start == date(2026, 9, 7)
    assert end == date(2026, 9, 13)


def test_last_completed_week_on_sunday():
    # Sunday itself counts as the completed week (Sunday-evening automation)
    start, end = last_completed_week(date(2026, 9, 20))
    assert start == date(2026, 9, 14)
    assert end == date(2026, 9, 20)


def test_last_completed_week_on_monday():
    # Monday -> the week that just ended yesterday
    start, end = last_completed_week(date(2026, 9, 21))
    assert start == date(2026, 9, 14)
    assert end == date(2026, 9, 20)


def test_group_games_by_week_splits_and_sorts():
    tg1 = make_team_game(1, date(2026, 9, 20), "18:00")  # W38
    tg2 = make_team_game(2, date(2026, 9, 14), "10:00")  # W38, earlier
    tg3 = make_team_game(3, date(2026, 9, 21), "12:00")  # W39

    grouped = group_games_by_week([tg1, tg2, tg3])

    assert list(grouped.keys()) == ["2026-W38", "2026-W39"]
    assert [tg.game.id for tg in grouped["2026-W38"]] == [2, 1]
    assert [tg.game.id for tg in grouped["2026-W39"]] == [3]


def test_group_by_category_orders_by_first_game_start_time():
    d = date(2026, 9, 14)
    games = [
        make_team_game(1, d, "14:00", category="Junioren D Rot"),
        make_team_game(2, d, "09:00", category="Herren Aktive GF 4. Liga"),
        make_team_game(3, d, "11:30", category="Junioren U14 B"),
        make_team_game(4, d, "10:15", category="Damen Aktive KF 3. Liga"),
    ]
    grouped = group_by_category(games)
    # Sorted by each category's earliest game time, not seniority/alphabet.
    assert list(grouped.keys()) == [
        "Herren Aktive GF 4. Liga",  # 09:00
        "Damen Aktive KF 3. Liga",  # 10:15
        "Junioren U14 B",  # 11:30
        "Junioren D Rot",  # 14:00
    ]


def test_group_by_category_orders_by_date_before_time():
    games = [
        make_team_game(1, date(2026, 9, 14), "09:00", category="Saturday Team"),
        make_team_game(2, date(2026, 9, 13), "20:00", category="Friday Team"),
    ]
    grouped = group_by_category(games)
    assert list(grouped.keys()) == ["Friday Team", "Saturday Team"]


def test_group_by_category_sorts_games_within_category():
    tg1 = make_team_game(1, date(2026, 9, 20), "18:00", category="Herren")
    tg2 = make_team_game(2, date(2026, 9, 14), "10:00", category="Herren")
    grouped = group_by_category([tg1, tg2])
    assert [tg.game.id for tg in grouped["Herren"]] == [2, 1]


def test_paginate_by_category_keeps_categories_together():
    d = date(2026, 9, 14)
    categorized = {
        "Herren": [make_team_game(i, d) for i in range(3)],
        "Damen": [make_team_game(i, d) for i in range(3, 6)],
        "Junioren D": [make_team_game(i, d) for i in range(6, 8)],
    }
    # Big enough for exactly one 3-game category, too small for two.
    capacity = layout.category_height(3, "results") + 1
    pages = paginate_by_category(categorized, kind="results", capacity=capacity)
    assert list(pages[0].keys()) == ["Herren"]
    assert list(pages[1].keys()) == ["Damen"]
    assert list(pages[2].keys()) == ["Junioren D"]


def test_paginate_by_category_packs_small_categories_together():
    d = date(2026, 9, 14)
    categorized = {
        "A": [make_team_game(1, d)],
        "B": [make_team_game(2, d)],
    }
    capacity = 2 * layout.category_height(1, "results")
    pages = paginate_by_category(categorized, kind="results", capacity=capacity)
    assert len(pages) == 1
    assert list(pages[0].keys()) == ["A", "B"]


def test_paginate_by_category_oversized_category_gets_its_own_page():
    d = date(2026, 9, 14)
    categorized = {"Huge": [make_team_game(i, d) for i in range(20)]}
    tiny_capacity = layout.category_height(1, "results")
    pages = paginate_by_category(categorized, kind="results", capacity=tiny_capacity)
    assert len(pages) == 1
    assert len(pages[0]["Huge"]) == 20


def test_paginate_by_category_default_capacity_matches_layout():
    d = date(2026, 9, 14)
    categorized = {"Herren": [make_team_game(1, d)]}
    default_pages = paginate_by_category(categorized, kind="results")
    explicit_pages = paginate_by_category(
        categorized, kind="results", capacity=layout.FEED_PROFILE.page_capacity()
    )
    assert default_pages == explicit_pages


def test_paginate_by_category_max_categories_caps_page_even_with_room_to_spare():
    d = date(2026, 9, 14)
    # Plenty of pixel capacity for all 5, but max_categories=4 should still
    # split into 2 pages - balanced 3+2 rather than a maxed-out 4+1 (see the
    # dedicated balancing tests below).
    categorized = {
        letter: [make_team_game(i, d) for i in range(2)] for letter in "ABCDE"
    }
    pages = paginate_by_category(categorized, kind="announce", max_categories=4)
    assert list(pages[0].keys()) == ["A", "B", "C"]
    assert list(pages[1].keys()) == ["D", "E"]


def test_paginate_by_category_max_games_caps_page_of_high_game_count_categories():
    d = date(2026, 9, 14)
    # 4 categories x 3 games = 12 games; a plain greedy fill would pack 3
    # categories (9 games, right at the cap) then leave 1 alone on page 2.
    # Balancing then kicks in: 2 pages are still needed, but split evenly
    # as 2+2 (6 games each, both within max_games) instead of 3+1.
    categorized = {
        letter: [make_team_game(i, d) for i in range(3)] for letter in "ABCD"
    }
    pages = paginate_by_category(
        categorized, kind="announce", max_categories=4, max_games=9
    )
    assert list(pages[0].keys()) == ["A", "B"]
    assert list(pages[1].keys()) == ["C", "D"]


def test_paginate_by_category_balances_seven_categories_into_four_plus_three():
    d = date(2026, 9, 14)
    # The user's own worked example: 7 categories, 2 games each. A plain
    # greedy fill under max_categories=4 would give 4+3 here anyway (7/4
    # rounds up to 2 pages, and greedy happens to land evenly) - this
    # confirms the balanced path reproduces that same expected split.
    categorized = {
        letter: [make_team_game(i, d) for i in range(2)] for letter in "ABCDEFG"
    }
    pages = paginate_by_category(categorized, kind="announce", max_categories=4, max_games=20)
    assert [len(p) for p in pages] == [4, 3]
    assert list(pages[0].keys()) == ["A", "B", "C", "D"]
    assert list(pages[1].keys()) == ["E", "F", "G"]


def test_paginate_by_category_falls_back_to_greedy_when_balancing_is_infeasible():
    d = date(2026, 9, 14)
    # A single oversized category (5 games) can't be evenly redistributed
    # alongside three 1-game categories within the 2 pages greedy needs
    # under max_games=5 - balancing must fall back to the greedy result
    # instead of silently producing more pages than were targeted.
    categorized = {
        "Huge": [make_team_game(i, d) for i in range(5)],
        "A": [make_team_game(10, d)],
        "B": [make_team_game(11, d)],
        "C": [make_team_game(12, d)],
    }
    pages = paginate_by_category(categorized, kind="announce", max_games=5)
    assert list(pages[0].keys()) == ["Huge"]
    assert list(pages[1].keys()) == ["A", "B", "C"]


def test_paginate_by_category_max_games_allows_full_max_categories_when_games_are_few():
    d = date(2026, 9, 14)
    # 4 categories x 2 games = 8 games, under max_games=9, so all 4 fit together.
    categorized = {
        letter: [make_team_game(i, d) for i in range(2)] for letter in "ABCD"
    }
    pages = paginate_by_category(
        categorized, kind="announce", max_categories=4, max_games=9
    )
    assert len(pages) == 1
    assert list(pages[0].keys()) == ["A", "B", "C", "D"]


from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from tvo_social.grouping import resolve_period

ZURICH = ZoneInfo("Europe/Zurich")


def at(day: date, hour: int = 12, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZURICH)


MON_12, SUN_18 = date(2026, 10, 12), date(2026, 10, 18)
MON_5, SUN_11 = date(2026, 10, 5), date(2026, 10, 11)
SAT_17 = date(2026, 10, 17)
SAT_24, SUN_25 = date(2026, 10, 24), date(2026, 10, 25)
SAT_31, SUN_1 = date(2026, 10, 31), date(2026, 11, 1)


def results(mode="current", now=None, anchor=None, played=(), scope="day"):
    return resolve_period("results", mode, now or at(SAT_17), anchor, played, scope)


def announce(mode="upcoming", now=None, anchor=None, scope="day"):
    return resolve_period("announce", mode, now or at(SAT_17), anchor, scope=scope)


# --- a picked date + scope: day / weekend / week, for EVERY weekday and kind ---

WEEK_DAYS = [
    (MON_12 + timedelta(days=i), name)
    for i, name in enumerate(
        ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    )
]
SCOPES = ("day", "weekend", "week")


def expected_period(scope, day):
    """The expected period for the week of Mon 12.10. - Sun 18.10.2026."""
    return {"day": (day, day), "weekend": (SAT_17, SUN_18), "week": (MON_12, SUN_18)}[scope]


@pytest.mark.parametrize("day,name", WEEK_DAYS)
@pytest.mark.parametrize("scope", SCOPES)
@pytest.mark.parametrize("kind", ["results", "announce"])
def test_picked_date_with_every_scope_for_every_weekday(kind, scope, day, name):
    mode = "current" if kind == "results" else "upcoming"
    for now in (at(date(2026, 1, 1)), at(SAT_17, 14, 27), at(date(2026, 11, 15), 23, 59)):
        assert resolve_period(kind, mode, now, anchor=day, scope=scope) == (
            expected_period(scope, day),
            None,
        ), name


@pytest.mark.parametrize("kind", ["results", "announce"])
def test_picked_date_without_a_scope_means_just_that_day(kind):
    mode = "current" if kind == "results" else "upcoming"
    for _, day_in_week in [(0, d) for d, _ in WEEK_DAYS]:
        assert resolve_period(kind, mode, at(SAT_17), anchor=day_in_week) == ((day_in_week, day_in_week), None)


@pytest.mark.parametrize("scope", SCOPES)
@pytest.mark.parametrize("kind", ["results", "announce"])
def test_picked_date_scopes_hold_for_every_day_of_two_years_including_year_boundaries(kind, scope):
    mode = "current" if kind == "results" else "upcoming"
    d = date(2025, 1, 1)
    while d <= date(2027, 1, 7):
        (first, last), note = resolve_period(kind, mode, at(date(2026, 6, 1)), anchor=d, scope=scope)
        monday = d - timedelta(days=d.weekday())
        assert note is None, d
        if scope == "day":
            assert (first, last) == (d, d), d
        elif scope == "weekend":
            assert (first, last) == (monday + timedelta(days=5), monday + timedelta(days=6)), d
            assert first.weekday() == 5 and last.weekday() == 6, d
        else:
            assert (first, last) == (monday, monday + timedelta(days=6)), d
            assert first.weekday() == 0 and last.weekday() == 6, d
        d += timedelta(days=1)


def test_picked_date_year_boundary_examples():
    # Thu 31.12.2026 lies in the week Mon 28.12.2026 - Sun 03.01.2027
    assert results(anchor=date(2026, 12, 31), scope="day")[0] == (date(2026, 12, 31), date(2026, 12, 31))
    assert results(anchor=date(2026, 12, 31), scope="weekend")[0] == (date(2027, 1, 2), date(2027, 1, 3))
    assert results(anchor=date(2026, 12, 31), scope="week")[0] == (date(2026, 12, 28), date(2027, 1, 3))
    assert results(anchor=date(2027, 1, 1), scope="week")[0] == (date(2026, 12, 28), date(2027, 1, 3))
    assert announce(anchor=date(2027, 1, 3), scope="weekend")[0] == (date(2027, 1, 2), date(2027, 1, 3))
    assert announce(anchor=date(2024, 12, 30), scope="week")[0] == (date(2024, 12, 30), date(2025, 1, 5))
    assert announce(anchor=date(2024, 12, 30), scope="weekend")[0] == (date(2025, 1, 4), date(2025, 1, 5))


def test_picked_date_ignores_the_mode_the_time_and_the_played_dates():
    # Day / weekend / week never fall back to another week, whatever else is known.
    elsewhere = [date(2026, 11, 2), date(2026, 11, 3)]
    for scope, expected in (
        ("day", (date(2026, 11, 15), date(2026, 11, 15))),
        ("weekend", (date(2026, 11, 14), date(2026, 11, 15))),
        ("week", (date(2026, 11, 9), date(2026, 11, 15))),
    ):
        for mode in ("current", "last"):
            assert results(mode, at(date(2030, 5, 5)), anchor=date(2026, 11, 15), played=elsewhere, scope=scope) == (
                expected,
                None,
            )
        for mode in ("upcoming", "after-next"):
            assert announce(mode, at(date(2030, 5, 5)), anchor=date(2026, 11, 15), scope=scope) == (expected, None)


def test_unknown_scope_is_rejected():
    with pytest.raises(ValueError):
        results(anchor=SAT_17, scope="month")


def test_formatting_helpers():
    from tvo_social.grouping import describe_period, format_day, format_range

    assert format_day(date(2026, 11, 15)) == "So 15.11.2026"
    assert format_range(date(2026, 11, 14), date(2026, 11, 15)) == "Sa 14.11. - So 15.11."
    assert format_range(date(2026, 12, 28), date(2027, 1, 3)) == "Mo 28.12.2026 - So 03.01.2027"
    assert describe_period(date(2026, 11, 15), date(2026, 11, 15), "day") == "am So 15.11.2026"
    assert describe_period(date(2026, 11, 14), date(2026, 11, 15), "weekend") == "am Wochenende Sa 14.11. - So 15.11."
    assert describe_period(date(2026, 11, 9), date(2026, 11, 15), "week") == "in der Woche Mo 09.11. - So 15.11."


# --- results: current / last / fallback ---


def test_results_current_week_with_played_games_is_mon_to_sun():
    window, note = results(now=at(SAT_17, 14, 27), played=[SAT_17, date(2026, 10, 11)])
    assert window == (MON_12, SUN_18) and note is None


def test_results_include_a_midweek_game_once_played():
    window, note = results(now=at(date(2026, 10, 15)), played=[date(2026, 10, 13), date(2026, 10, 11)])
    assert window == (MON_12, SUN_18) and note is None


def test_results_fall_back_to_latest_week_with_played_games():
    window, note = results(
        now=at(date(2026, 10, 14)), played=[date(2026, 10, 3), date(2026, 10, 11), date(2026, 10, 10)]
    )
    assert window == (MON_5, SUN_11)
    assert note


def test_results_fallback_can_land_on_a_midweek_game():
    window, _ = results(now=at(date(2026, 10, 19)), played=[date(2026, 10, 14), date(2026, 10, 4)])
    assert window == (MON_12, SUN_18)


def test_results_without_any_games_is_the_current_week():
    window, note = results(now=at(date(2026, 10, 14)))
    assert window == (MON_12, SUN_18) and note is None


def test_results_last_is_the_previous_week():
    assert results("last", at(SAT_17))[0] == (MON_5, SUN_11)
    assert results("last", at(date(2026, 10, 19)))[0] == (MON_12, SUN_18)


# --- announcements: coming / after-next weekend, incl. the Sunday edge case ---


@pytest.mark.parametrize(
    "day,expected",
    [
        (date(2026, 10, 12), (SAT_17, SUN_18)),  # Monday
        (date(2026, 10, 13), (SAT_17, SUN_18)),  # Tuesday
        (date(2026, 10, 14), (SAT_17, SUN_18)),  # Wednesday
        (date(2026, 10, 15), (SAT_17, SUN_18)),  # Thursday
        (date(2026, 10, 16), (SAT_17, SUN_18)),  # Friday
        (SAT_17, (SAT_17, SUN_18)),  # Saturday: the weekend is in progress, still coming
        (SUN_18, (SAT_24, SUN_25)),  # Sunday: this weekend is ending, so next weekend
    ],
)
def test_announce_upcoming_weekend_for_every_weekday(day, expected):
    assert announce("upcoming", at(day))[0] == expected
    shifted = (expected[0] + timedelta(days=7), expected[1] + timedelta(days=7))
    assert announce("after-next", at(day))[0] == shifted


def test_announce_boundaries_monday_midnight_and_sunday_last_minute():
    assert announce("upcoming", at(date(2026, 10, 12), 0, 0))[0] == (SAT_17, SUN_18)
    assert announce("upcoming", at(date(2026, 10, 11), 23, 59))[0] == (SAT_17, SUN_18)  # Sunday before
    assert announce("upcoming", at(SUN_18, 23, 59))[0] == (SAT_24, SUN_25)
    assert announce("upcoming", at(date(2026, 10, 19), 0, 0))[0] == (SAT_24, SUN_25)  # next Monday 00:00
    assert announce("after-next", at(SUN_18, 23, 59))[0] == (SAT_31, SUN_1)


def test_announce_across_the_year_boundary():
    assert announce("upcoming", at(date(2026, 12, 27)))[0] == (date(2027, 1, 2), date(2027, 1, 3))  # Sunday
    assert announce("upcoming", at(date(2026, 12, 28)))[0] == (date(2027, 1, 2), date(2027, 1, 3))  # Monday
    assert announce("after-next", at(date(2026, 12, 27)))[0] == (date(2027, 1, 9), date(2027, 1, 10))
    assert announce("upcoming", at(date(2026, 12, 31)))[0] == (date(2027, 1, 2), date(2027, 1, 3))


# --- results boundaries: Monday 00:00 / Sunday 23:59 ---


def test_results_boundaries_monday_midnight_and_sunday_last_minute():
    assert results(now=at(SUN_18, 23, 59), played=[SAT_17])[0] == (MON_12, SUN_18)
    window, note = results(now=at(date(2026, 10, 19), 0, 0), played=[SAT_17])  # next Monday 00:00
    assert window == (MON_12, SUN_18) and note  # new week empty, falls back to the one just ended
    assert results("last", at(SUN_18, 23, 59))[0] == (MON_5, SUN_11)
    assert results("last", at(date(2026, 10, 19), 0, 0))[0] == (MON_12, SUN_18)


def test_results_across_the_year_boundary():
    assert results(now=at(date(2027, 1, 1)), played=[date(2026, 12, 30)])[0] == (
        date(2026, 12, 28),
        date(2027, 1, 3),
    )
    window, note = results(now=at(date(2027, 1, 4)), played=[date(2027, 1, 2)])
    assert window == (date(2026, 12, 28), date(2027, 1, 3)) and note
    assert results("last", at(date(2027, 1, 5)))[0] == (date(2026, 12, 28), date(2027, 1, 3))


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        resolve_period("results", "upcoming", at(SAT_17))
    with pytest.raises(ValueError):
        resolve_period("announce", "current", at(SAT_17))


def test_paginate_balance_flag_evens_out_pages_even_without_caps():
    d = date(2026, 10, 17)
    categorized = {
        "A": [make_team_game(i, d) for i in range(3)],
        "B": [make_team_game(i, d) for i in range(3, 6)],
        "C": [make_team_game(i, d) for i in range(6, 8)],
        "D": [make_team_game(i, d) for i in range(8, 10)],
    }
    greedy = paginate_by_category(categorized, kind="results")
    balanced = paginate_by_category(categorized, kind="results", balance=True)
    assert [len(p) for p in greedy] == [3, 1]
    assert [len(p) for p in balanced] == [2, 2]
