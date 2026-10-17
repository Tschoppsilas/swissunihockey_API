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
]
PLANNED = [
    tg(3, date(2026, 10, 17), "10:00", "Junioren D Regional", None, "UHC Gamma"),  # overdue, no score
    tg(4, date(2026, 10, 17), "16:30", "Junioren E Regional", None, "UHC Delta"),  # later today
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


def test_saturday_shows_only_games_already_played_or_overdue(monkeypatch):
    out = run(monkeypatch, datetime(2026, 10, 17, 14, 27, tzinfo=ZURICH))
    assert "Zeitraum: 17.10.2026 - 18.10.2026" in out
    assert "Junioren C Regional" in out and "5:3" in out
    assert "Junioren D Regional" in out and "(Resultat folgt)" in out
    assert "Junioren E Regional" not in out  # starts at 16:30, not yet played
    assert "Damen Aktive KF" not in out  # tomorrow
    assert "Herren Aktive" not in out  # last weekend
    assert "Titel: RESULTATE - 17.10." in out
    assert "FEHLENDES RESULTAT: Junioren D Regional" in out
    assert "Hinweis" not in out


def test_saturday_evening_includes_the_later_game_as_missing(monkeypatch):
    out = run(monkeypatch, datetime(2026, 10, 17, 18, 30, tzinfo=ZURICH))
    assert "Junioren E Regional" in out and "(Resultat folgt)" in out


def test_midweek_falls_back_to_last_weekend_with_a_note(monkeypatch):
    out = run(monkeypatch, datetime(2026, 10, 14, 9, 0, tzinfo=ZURICH))
    assert "Zeitraum: 10.10.2026 - 11.10.2026" in out
    assert "Hinweis: Am aktuellen Wochenende wurde noch nichts gespielt" in out
    assert "Herren Aktive GF 4. Liga" in out and "1:5" in out
    assert "Titel: RESULTATE - 11.10." in out


def test_last_weekend_option(monkeypatch):
    out = run(monkeypatch, datetime(2026, 10, 17, 14, 27, tzinfo=ZURICH), "--weekend", "last")
    assert "Zeitraum: 10.10.2026 - 11.10.2026" in out
    assert "Herren Aktive GF 4. Liga" in out and "Junioren C" not in out


def test_date_option(monkeypatch):
    out = run(monkeypatch, datetime(2026, 10, 19, 9, 0, tzinfo=ZURICH), "--date", "2026-10-11")
    assert "Zeitraum: 10.10.2026 - 11.10.2026" in out
    assert "Herren Aktive GF 4. Liga" in out


def test_no_games_message_kept_for_the_web_progress_parser(monkeypatch):
    out = run(monkeypatch, datetime(2026, 10, 17, 14, 27, tzinfo=ZURICH), "--date", "2026-09-01")
    assert "Keine Resultate im Zeitraum gefunden." in out
