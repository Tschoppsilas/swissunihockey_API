from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from click.testing import CliRunner

from tvo_social import cli
from tvo_social.models import Game, TeamGame

ZURICH = ZoneInfo("Europe/Zurich")


def tg(id, d, time, category, goals=None, opponent="Gegner"):
    game = Game(
        id=id, date=d, time=time, home_team="TV Oberwil BL", away_team=opponent,
        home_team_id=1, away_team_id=2, venue="Halle", league_text=category, category_text=category,
        played=goals is not None,
        goals_home=goals[0] if goals else None, goals_away=goals[1] if goals else None,
    )
    return TeamGame(
        game=game, category=category, opponent=opponent,
        our_goals=goals[0] if goals else None, opp_goals=goals[1] if goals else None, is_home=True,
    )


PLAYED = [
    tg(1, date(2026, 10, 17), "12:00", "Junioren C Regional", (5, 3), "UHC Alpha"),
    tg(2, date(2026, 10, 11), "12:40", "Herren Aktive GF 4. Liga", (1, 5), "UHC Beta"),
    tg(6, date(2026, 10, 14), "20:00", "Herren Cup", (4, 2), "UHC Zeta"),  # midweek game this week
]
PLANNED = [
    tg(3, date(2026, 10, 17), "10:00", "Junioren D Regional", None, "UHC Gamma"),  # today, no score
    tg(4, date(2026, 10, 17), "16:30", "Junioren E Regional", None, "UHC Delta"),  # today, no score
    tg(5, date(2026, 10, 18), "10:00", "Damen Aktive KF 3. Liga", None, "UHC Eps"),  # tomorrow
]


def run(monkeypatch, now, *args):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(cli, "datetime", FixedDatetime)
    monkeypatch.setattr(
        cli, "load_config",
        lambda: SimpleNamespace(api_base="http://x", output_dir=Path("out"), missing_result_text="RESULTAT FOLGT"),
    )
    monkeypatch.setattr(cli, "get_teams", lambda client, cfg: [])
    monkeypatch.setattr(
        cli, "_fetch_team_games",
        lambda client, teams, status, order, season=None: list(PLAYED if status == "played" else PLANNED),
    )
    result = CliRunner().invoke(cli.main, ["results", "--dry-run", *args])
    assert result.exit_code == 0, result.output
    return result.output


def test_saturday_shows_whole_week_played_games_and_todays_missing_results(monkeypatch):
    out = run(monkeypatch, datetime(2026, 10, 17, 14, 27, tzinfo=ZURICH))
    assert "Zeitraum: 12.10.2026 - 18.10.2026" in out
    assert "Junioren C Regional" in out and "5:3" in out
    assert "Herren Cup" in out and "4:2" in out  # Wednesday game of this week
    assert "Junioren D Regional" in out and "Junioren E Regional" in out  # dated today, no score yet
    assert out.count("(Resultat folgt)") == 2
    assert "Damen Aktive KF" not in out  # tomorrow
    assert "Herren Aktive" not in out  # previous week
    assert "Titel: RESULTATE - 14.-17.10." in out
    assert "FEHLENDES RESULTAT: Junioren D Regional" in out
    assert "Hinweis" not in out


def test_game_dated_today_without_score_is_marked_even_in_the_morning(monkeypatch):
    out = run(monkeypatch, datetime(2026, 10, 17, 8, 0, tzinfo=ZURICH))
    assert "Junioren E Regional" in out and "(Resultat folgt)" in out


def test_week_without_played_games_falls_back_with_a_note(monkeypatch):
    out = run(monkeypatch, datetime(2026, 10, 26, 9, 0, tzinfo=ZURICH))  # Monday, week 27.10.-02.11.
    assert "Zeitraum: 12.10.2026 - 18.10.2026" in out
    assert "Hinweis: Diese Woche wurde noch nichts gespielt" in out
    assert "Herren Cup" in out and "Junioren C Regional" in out


def test_last_week_option(monkeypatch):
    out = run(monkeypatch, datetime(2026, 10, 17, 14, 27, tzinfo=ZURICH), "--weekend", "last")
    assert "Zeitraum: 05.10.2026 - 11.10.2026" in out
    assert "Herren Aktive GF 4. Liga" in out and "Junioren C" not in out
    assert "Titel: RESULTATE - 11.10." in out


def test_date_option_means_the_whole_week(monkeypatch):
    out = run(monkeypatch, datetime(2026, 10, 19, 9, 0, tzinfo=ZURICH), "--date", "2026-10-14")
    assert "Zeitraum: 12.10.2026 - 18.10.2026" in out
    assert "Herren Cup" in out and "Junioren C Regional" in out


def test_no_games_message_kept_for_the_web_progress_parser(monkeypatch):
    out = run(monkeypatch, datetime(2026, 10, 17, 14, 27, tzinfo=ZURICH), "--date", "2026-09-01")
    assert "Keine Resultate im Zeitraum gefunden." in out
