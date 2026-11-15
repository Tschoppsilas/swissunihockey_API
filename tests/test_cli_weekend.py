from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from click.testing import CliRunner

from tvo_social import cli
from tvo_social.models import Game, TeamGame

ZURICH = ZoneInfo("Europe/Zurich")
HOME_VENUE = "Thomasgarten (Oberwil BL)"


def tg(id, d, time, category, venue, opponent="Gegner"):
    game = Game(
        id=id, date=d, time=time, home_team="TV Oberwil BL", away_team=opponent,
        home_team_id=1, away_team_id=2, venue=venue, league_text=category, category_text=category,
        played=False, goals_home=None, goals_away=None,
    )
    return TeamGame(
        game=game, category=category, opponent=opponent, our_goals=None, opp_goals=None, is_home=True
    )


PLANNED = [
    tg(1, date(2026, 11, 11), "20:00", "Herren Cup", "Halle Mitte"),  # Wednesday of the week 9.-15.11.
    tg(2, date(2026, 11, 14), "09:00", "Junioren C", HOME_VENUE),  # Saturday 14.11.
    tg(3, date(2026, 11, 15), "10:00", "Junioren D", "Halle Nord"),  # Sunday 15.11.
    tg(4, date(2026, 11, 21), "10:00", "Damen", HOME_VENUE),  # next Saturday
    tg(5, date(2026, 11, 22), "12:00", "Herren", ""),  # next Sunday, venue not assigned yet
    tg(6, date(2026, 11, 28), "10:00", "Junioren E", "Halle Sued"),  # the Saturday after
]


def run(monkeypatch, now, *args, planned=None, command="weekend"):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            # Like the real clock: converts to the requested zone, otherwise stays as given.
            return now.astimezone(tz) if tz is not None else now

    monkeypatch.setattr(cli, "datetime", FixedDatetime)
    monkeypatch.setattr(
        cli, "load_config",
        lambda: SimpleNamespace(
            api_base="http://x", output_dir=Path("out"), missing_venue_text="ORT FOLGT",
            missing_result_text="RESULTAT FOLGT", home_venue=HOME_VENUE,
        ),
    )
    monkeypatch.setattr(cli, "get_teams", lambda client, cfg: [])
    monkeypatch.setattr(
        cli, "_fetch_team_games",
        lambda client, teams, status, order, season=None: list(PLANNED if planned is None else planned)
        if status == "planned" else [],
    )
    result = CliRunner().invoke(cli.main, [command, "--dry-run", *args])
    assert result.exit_code == 0, result.output
    return result.output


def test_default_on_a_sunday_is_the_next_weekend(monkeypatch):
    out = run(monkeypatch, datetime(2026, 11, 15, 13, 40, tzinfo=ZURICH))
    assert "Zeitraum: 21.11.2026 - 22.11.2026" in out
    assert "2026-W47: 2 Spiele -> 1 Bild(er)" in out
    assert "Junioren D" not in out


def test_default_on_a_saturday_is_the_weekend_in_progress(monkeypatch):
    out = run(monkeypatch, datetime(2026, 11, 14, 8, 0, tzinfo=ZURICH))
    assert "Zeitraum: 14.11.2026 - 15.11.2026" in out
    assert "2026-W46: 2 Spiele -> 1 Bild(er)" in out  # Saturday + Sunday, not the Wednesday game


def test_default_on_monday_midnight_is_this_weeks_weekend(monkeypatch):
    out = run(monkeypatch, datetime(2026, 11, 16, 0, 0, tzinfo=ZURICH))
    assert "Zeitraum: 21.11.2026 - 22.11.2026" in out


def test_after_next_weekend(monkeypatch):
    out = run(monkeypatch, datetime(2026, 11, 15, 13, 40, tzinfo=ZURICH), "--weekend", "after-next")
    assert "Zeitraum: 28.11.2026 - 29.11.2026" in out
    assert "2026-W48: 1 Spiele -> 1 Bild(er)" in out


NOW = datetime(2026, 11, 20, 9, 0, tzinfo=ZURICH)
WEEK_9_15 = [f"2026-11-{d:02d}" for d in range(9, 16)]  # Monday 9.11. .. Sunday 15.11.


@pytest.mark.parametrize(
    "pick,expected_games",
    [
        ("2026-11-09", None),  # Mon
        ("2026-11-10", None),  # Tue
        ("2026-11-11", "Herren Cup"),  # Wed
        ("2026-11-12", None),  # Thu
        ("2026-11-13", None),  # Fri
        ("2026-11-14", "Junioren C"),  # Sat
        ("2026-11-15", "Junioren D"),  # Sun
    ],
)
def test_a_picked_date_alone_takes_only_that_days_games(monkeypatch, pick, expected_games):
    out = run(monkeypatch, NOW, "--date", pick)
    day = datetime.strptime(pick, "%Y-%m-%d")
    if expected_games is None:
        assert f"Zeitraum: {day:%d.%m.%Y}" in out
        assert out.rstrip().splitlines()[-1].startswith("Keine Spiele am ")
        assert "Titel:" not in out and "Bild(er)" not in out
    else:
        assert f"Zeitraum: {day:%d.%m.%Y}\n" in out
        assert "2026-W46: 1 Spiele -> 1 Bild(er)" in out
        assert f"Titel: GAME WEEKEND - {day:%d.%m.}" in out


def test_title_for_a_single_day_names_only_that_day(monkeypatch):
    assert "Titel: GAME WEEKEND - 15.11." in run(monkeypatch, NOW, "--date", "2026-11-15")
    assert "Titel: GAME WEEKEND - 14.11." in run(monkeypatch, NOW, "--date", "2026-11-14")


@pytest.mark.parametrize("pick", WEEK_9_15)
def test_scope_weekend_is_saturday_and_sunday_of_the_picked_days_week(monkeypatch, pick):
    out = run(monkeypatch, NOW, "--date", pick, "--scope", "weekend")
    assert "Zeitraum: 14.11.2026 - 15.11.2026" in out
    assert "2026-W46: 2 Spiele -> 1 Bild(er)" in out  # not the Wednesday game
    assert "Titel: GAME WEEKEND - 14.-15.11." in out


@pytest.mark.parametrize("pick", WEEK_9_15)
def test_scope_week_is_monday_to_sunday_of_the_picked_days_week(monkeypatch, pick):
    out = run(monkeypatch, NOW, "--date", pick, "--scope", "week")
    assert "Zeitraum: 09.11.2026 - 15.11.2026" in out
    assert "2026-W46: 3 Spiele -> 1 Bild(er)" in out  # incl. the Wednesday game
    assert "Titel: GAME WEEKEND - 11.-15.11." in out


def test_home_game_gets_a_feed_post_when_its_day_is_picked(monkeypatch):
    out = run(monkeypatch, NOW, "--date", "2026-11-14")  # Saturday: the home game
    assert "1 Heimspiel(e) gefunden - erzeuge zusaetzlich den Feed-Post." in out
    assert [l for l in out.splitlines() if l.startswith("2026-W46:")] == [
        "2026-W46: 1 Spiele -> 1 Bild(er)",  # story
        "2026-W46: 1 Spiele -> 1 Bild(er)",  # feed
    ]


def test_story_and_feed_follow_the_chosen_scope(monkeypatch):
    out = run(monkeypatch, NOW, "--date", "2026-11-13", "--scope", "week")
    assert [l for l in out.splitlines() if l.startswith("2026-W46:")] == [
        "2026-W46: 3 Spiele -> 1 Bild(er)",  # story: every game of the week
        "2026-W46: 1 Spiele -> 1 Bild(er)",  # feed: only the home game
    ]


def test_a_day_without_home_games_gets_no_feed_post(monkeypatch):
    out = run(monkeypatch, NOW, "--date", "2026-11-15")  # Sunday: away game only
    assert "Kein Heimspiel im Zeitraum - kein Feed-Post noetig." in out


def test_no_fallback_when_the_chosen_day_has_no_games(monkeypatch):
    out = run(monkeypatch, NOW, "--date", "2026-11-16")  # Monday: nothing, although the week after has games
    assert "Keine Spiele am Mo 16.11.2026." in out
    assert "Bild(er)" not in out


def test_no_games_messages_name_the_chosen_scope(monkeypatch):
    assert "Keine Spiele am Do 24.12.2026." in run(monkeypatch, NOW, "--date", "2026-12-24")
    weekend_out = run(monkeypatch, NOW, "--date", "2026-12-24", "--scope", "weekend")
    assert weekend_out.splitlines()[-1] == "Keine Spiele am Wochenende Sa 26.12. - So 27.12."
    week_out = run(monkeypatch, NOW, "--date", "2026-12-24", "--scope", "week")
    assert week_out.splitlines()[-1] == "Keine Spiele in der Woche Mo 21.12. - So 27.12."


def test_missing_venue_is_still_reported(monkeypatch):
    out = run(monkeypatch, datetime(2026, 11, 15, 13, 40, tzinfo=ZURICH))
    assert "FEHLENDE HALLE: Herren" in out


def test_without_a_date_nothing_changes_and_no_scope_is_accepted(monkeypatch):
    assert "Zeitraum: 21.11.2026 - 22.11.2026" in run(monkeypatch, datetime(2026, 11, 15, 13, 40, tzinfo=ZURICH))
    result = CliRunner().invoke(cli.main, ["weekend", "--dry-run", "--scope", "day"])
    assert result.exit_code == 2 and "--scope gilt nur zusammen mit --date" in result.output
    assert "Keine Spiele im Zeitraum gefunden." in run(
        monkeypatch, datetime(2026, 11, 15, 13, 40, tzinfo=ZURICH), planned=[]
    )


YEAR_END = [
    tg(21, date(2026, 12, 31), "10:00", "Herren", HOME_VENUE),  # Thursday
    tg(22, date(2027, 1, 2), "10:00", "Damen", "Halle Nord"),  # Saturday, next year
]


def test_year_boundary_for_every_scope(monkeypatch):
    day = run(monkeypatch, NOW, "--date", "2026-12-31", planned=YEAR_END)
    assert "Zeitraum: 31.12.2026\n" in day and "2026-W53: 1 Spiele -> 1 Bild(er)" in day
    weekend = run(monkeypatch, NOW, "--date", "2026-12-31", "--scope", "weekend", planned=YEAR_END)
    assert "Zeitraum: 02.01.2027 - 03.01.2027" in weekend and "2026-W53: 1 Spiele -> 1 Bild(er)" in weekend
    week = run(monkeypatch, NOW, "--date", "2027-01-01", "--scope", "week", planned=YEAR_END)
    assert "Zeitraum: 28.12.2026 - 03.01.2027" in week and "2026-W53: 2 Spiele -> 1 Bild(er)" in week


@pytest.mark.parametrize("scope", ["day", "weekend", "week"])
def test_results_every_weekday_follows_the_scope(monkeypatch, scope):
    played = [
        tg(9, date(2026, 11, 14), "09:00", "Junioren C", HOME_VENUE),
        tg(8, date(2026, 11, 11), "20:00", "Herren Cup", "Halle Mitte"),
    ]
    outputs = {}
    for pick in WEEK_9_15:
        out = run(
            monkeypatch, NOW, "--date", pick, "--scope", scope, command="results", planned=played
        )
        outputs[pick] = out
    first_lines = {pick: out.splitlines()[0] for pick, out in outputs.items()}
    if scope == "week":
        assert set(first_lines.values()) == {"Zeitraum: 09.11.2026 - 15.11.2026"}
    elif scope == "weekend":
        assert set(first_lines.values()) == {"Zeitraum: 14.11.2026 - 15.11.2026"}
    else:
        assert [first_lines[p] for p in WEEK_9_15] == [
            f"Zeitraum: {d:02d}.11.2026" for d in range(9, 16)
        ]


def test_week_boundary_uses_swiss_time_not_the_server_clock(monkeypatch):
    # Sunday 23:30 UTC is already Monday 00:30 in Zurich (CET): the coming weekend
    # must be computed from the Swiss date (Monday), not from the UTC date (Sunday).
    now_utc = datetime(2026, 11, 15, 23, 30, tzinfo=ZoneInfo("UTC"))
    out = run(monkeypatch, now_utc)
    assert "Zeitraum: 21.11.2026 - 22.11.2026" in out
    # a Sunday-23:30-UTC clock read as UTC would still be Sunday and give the same weekend as
    # the Swiss Monday only by luck: also pin the Saturday/Sunday edge where they differ
    out = run(monkeypatch, datetime(2026, 11, 14, 23, 30, tzinfo=ZoneInfo("UTC")))  # Sunday 00:30 Zurich
    assert "Zeitraum: 21.11.2026 - 22.11.2026" in out  # Sunday in Zurich: the next weekend, not 14.-15.11.
