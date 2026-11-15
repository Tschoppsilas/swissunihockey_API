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


@pytest.mark.parametrize("pick", ["2026-11-09", "2026-11-11", "2026-11-13", "2026-11-14", "2026-11-15"])
def test_a_picked_date_means_the_whole_week_whatever_the_weekday(monkeypatch, pick):
    out = run(monkeypatch, datetime(2026, 11, 20, 9, 0, tzinfo=ZURICH), "--date", pick)
    assert "Zeitraum: 09.11.2026 - 15.11.2026" in out
    assert "2026-W46: 3 Spiele -> 1 Bild(er)" in out  # incl. the Wednesday game
    assert "Titel: GAME WEEKEND - 11.-15.11." in out


def test_home_games_give_a_feed_post_and_the_story_covers_all_games(monkeypatch):
    out = run(monkeypatch, datetime(2026, 11, 20, 9, 0, tzinfo=ZURICH), "--date", "2026-11-15")
    assert "1 Heimspiel(e) gefunden - erzeuge zusaetzlich den Feed-Post." in out
    assert [l for l in out.splitlines() if l.startswith("2026-W46:")] == [
        "2026-W46: 3 Spiele -> 1 Bild(er)",  # story: every game of the week
        "2026-W46: 1 Spiele -> 1 Bild(er)",  # feed: only the home game
    ]


def test_no_home_games_means_no_feed_post(monkeypatch):
    out = run(monkeypatch, datetime(2026, 11, 20, 9, 0, tzinfo=ZURICH), "--date", "2026-11-26")
    assert "Zeitraum: 23.11.2026 - 29.11.2026" in out
    assert "Kein Heimspiel im Zeitraum - kein Feed-Post noetig." in out


def test_missing_venue_is_still_reported(monkeypatch):
    out = run(monkeypatch, datetime(2026, 11, 15, 13, 40, tzinfo=ZURICH))
    assert "FEHLENDE HALLE: Herren" in out


def test_period_without_games(monkeypatch):
    out = run(monkeypatch, datetime(2026, 11, 15, 13, 40, tzinfo=ZURICH), "--date", "2026-12-24")
    assert "Zeitraum: 21.12.2026 - 27.12.2026" in out
    assert "Keine Spiele im Zeitraum gefunden." in out


def test_results_for_every_weekday_of_the_same_week_agree(monkeypatch):
    played = [tg(9, date(2026, 11, 14), "09:00", "Junioren C", HOME_VENUE)]
    outputs = []
    for day in range(9, 16):  # Monday 9.11. .. Sunday 15.11.
        out = run(
            monkeypatch, datetime(2026, 11, 20, 9, 0, tzinfo=ZURICH), "--date", f"2026-11-{day:02d}",
            command="results", planned=played,
        )
        outputs.append([l for l in out.splitlines() if l.startswith(("Zeitraum:", "2026-W", "  Titel:"))])
    assert all(o == outputs[0] for o in outputs)
    assert outputs[0][0] == "Zeitraum: 09.11.2026 - 15.11.2026"


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
