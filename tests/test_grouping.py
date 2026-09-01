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
    # Plenty of pixel capacity for all 5, but max_categories=4 should still split.
    categorized = {
        letter: [make_team_game(i, d) for i in range(2)] for letter in "ABCDE"
    }
    pages = paginate_by_category(categorized, kind="announce", max_categories=4)
    assert list(pages[0].keys()) == ["A", "B", "C", "D"]
    assert list(pages[1].keys()) == ["E"]


def test_paginate_by_category_max_games_caps_page_of_high_game_count_categories():
    d = date(2026, 9, 14)
    # 4 categories x 3 games = 12 games; max_games=9 should stop after 3 (9 games),
    # even though max_categories=4 alone would have allowed a 4th.
    categorized = {
        letter: [make_team_game(i, d) for i in range(3)] for letter in "ABCD"
    }
    pages = paginate_by_category(
        categorized, kind="announce", max_categories=4, max_games=9
    )
    assert list(pages[0].keys()) == ["A", "B", "C"]
    assert list(pages[1].keys()) == ["D"]


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
