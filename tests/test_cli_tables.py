from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from click.testing import CliRunner

from tvo_social import cli
from tvo_social.models import Team
from tvo_social.templates.table_card import TableTemplate

ZURICH = ZoneInfo("Europe/Zurich")
CLUB = 696


def raw_entry(place, team_id, name, club=1, games=8, wo=0):
    return {
        "place": place, "teamid": team_id, "clubid": club, "teamname": name, "games": games, "wins": 4,
        "ties": 1, "defeats": 3, "goals-scored": 30, "goals-received": 25, "points": 13,
        "wins-overtime": wo, "defeats-overtime": 0, "games-without-score": 0,
    }


def hdr(league, season=2026):
    return {"season": season, "leaguetext": league, "leaguetype": "Meisterschaft"}


D_ENTRIES = [
    raw_entry(1, 430043, "TV Oberwil BL I", CLUB), raw_entry(2, 428478, "TV Oberwil BL II", CLUB),
    raw_entry(3, 5, "UHC Frenkendorf-Füllinsdorf"),
]
TEAMS = [
    Team(428478, "TV Oberwil BL", "Junioren D Regional", 344),
    Team(430043, "TV Oberwil BL", "Junioren D Regional", 344),
    Team(431471, "TV Oberwil BL", "Herren Aktive GF 4. Liga", 116),
    Team(432098, "TV Oberwil BL", "Junioren U18 C", 183),
    Team(429806, "TV Oberwil BL", "Junioren E Regional", 354),
    Team(7, "TV Oberwil BL", "Juniorinnen Zürich U17 B", 282),
]
TABLES = {
    428478: (hdr("Junioren D Regional"), D_ENTRIES),
    430043: (hdr("Junioren D Regional"), D_ENTRIES),
    431471: (hdr("Herren Aktive GF 4. Liga"), [raw_entry(1, 9, "UHC Foo"), raw_entry(2, 431471, "TV Oberwil BL", CLUB)]),
    432098: None,  # 404
    429806: (hdr("Junioren E Regional"), [raw_entry(1, 429806, "TV Oberwil BL I", CLUB), raw_entry(2, 9, "UHC Foo")]),
    7: (hdr("Juniorinnen Zürich U17 B"), [raw_entry(1, 7, "TV Oberwil BL", CLUB), raw_entry(2, 8, "UHC Bar", wo=1)]),
}


class FakeApiClient:
    requested = []

    def __init__(self, base_url):
        pass

    def get_team_table(self, team_id, season=None):
        FakeApiClient.requested.append((team_id, season))
        return TABLES.get(team_id)


@pytest.fixture
def setup(monkeypatch, tmp_path):
    FakeApiClient.requested = []
    config = SimpleNamespace(
        api_base="http://x", output_dir=tmp_path, club_id=CLUB, tables_exclude_categories=("Junioren E",),
    )
    monkeypatch.setattr(cli, "load_config", lambda: config)
    monkeypatch.setattr(cli, "ApiClient", FakeApiClient)
    monkeypatch.setattr(cli, "get_teams", lambda client, cfg: TEAMS)
    monkeypatch.setattr(cli, "load_team_labels", lambda: {430043: "D Rot", 428478: "D Weiss", 431471: "Herren"})

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 15, 14, 0, tzinfo=ZURICH)

    monkeypatch.setattr(cli, "datetime", FixedDatetime)
    return config


def run(*args):
    result = CliRunner().invoke(cli.main, ["tables", *args])
    assert result.exit_code == 0, result.output
    return result.output


def test_one_image_per_group_in_the_season_folder(setup, tmp_path):
    out = run()
    assert (tmp_path / "tables" / "2026" / "junioren-d-regional.png").is_file()
    assert (tmp_path / "tables" / "2026" / "herren-aktive-gf-4-liga.png").is_file()
    assert (tmp_path / "tables" / "2026" / "juniorinnen-zuerich-u17-b.png").is_file()
    assert len(list((tmp_path / "tables" / "2026").glob("*.png"))) == 3  # D group shared by two teams, E excluded
    assert "Tabelle: Junioren D Regional - 3 Teams, TVO: TVO D Rot, TVO D Weiss" in out
    assert "Tabelle: Herren Aktive GF 4. Liga - 2 Teams, TVO: TV Oberwil" in out


def test_the_excluded_category_is_logged_briefly_and_never_requested(setup):
    out = run()
    assert "Junioren E: ausgeschlossen (Konfiguration)" in out.splitlines()
    assert 429806 not in [team_id for team_id, _ in FakeApiClient.requested]


def test_missing_table_is_skipped_with_its_reason_and_no_image(setup, tmp_path):
    out = run()
    assert "UEBERSPRUNGEN: Junioren U18 C (Junioren U18 C): keine Tabelle (404)" in out
    assert "Zusammenfassung: 3 Bild(er), 1 Tabelle(n) uebersprungen" in out
    assert not list((tmp_path / "tables").rglob("*u18*"))


def test_console_output_is_pure_ascii_even_with_umlauts_in_the_data(setup):
    out = run()
    assert all(ord(ch) < 128 for ch in out), [ch for ch in out if ord(ch) >= 128]
    assert "Juniorinnen Zuerich U17 B" in out


def test_season_is_passed_on_and_names_the_folder(setup, tmp_path):
    TABLES[428478] = (hdr("Junioren D Regional", 2025), D_ENTRIES)
    TABLES[430043] = TABLES[428478]
    try:
        run("--season", "2025")
    finally:
        TABLES[428478] = (hdr("Junioren D Regional"), D_ENTRIES)
        TABLES[430043] = TABLES[428478]
    assert all(season == 2025 for _, season in FakeApiClient.requested)
    assert (tmp_path / "tables" / "2025" / "junioren-d-regional.png").is_file()


def test_label_and_stand_end_up_in_the_title_text(setup, monkeypatch):
    seen = []
    original = TableTemplate.render_to

    def spy(self, out_path, rows, show_overtime, subtitle, stand_text):
        seen.append((subtitle, stand_text, show_overtime))
        return original(self, out_path, rows, show_overtime, subtitle, stand_text)

    monkeypatch.setattr(TableTemplate, "render_to", spy)
    run("--label", "Winterpause", "--stand", "2026-12-20")
    assert ("Junioren D Regional", "Stand: 20.12.2026 · Winterpause", False) in seen
    seen.clear()
    run()
    assert all(text == "Stand: 15.11.2026" for _, text, _ in seen)  # default: today, no label


def test_overtime_columns_are_requested_only_for_tables_that_have_values(setup, monkeypatch):
    seen = {}
    original = TableTemplate.render_to

    def spy(self, out_path, rows, show_overtime, subtitle, stand_text):
        seen[subtitle] = show_overtime
        return original(self, out_path, rows, show_overtime, subtitle, stand_text)

    monkeypatch.setattr(TableTemplate, "render_to", spy)
    run()
    assert seen["Juniorinnen Zürich U17 B"] is True
    assert seen["Junioren D Regional"] is False


def test_dry_run_writes_nothing(setup, tmp_path):
    out = run("--dry-run")
    assert "(Trockenlauf) wuerde schreiben:" in out
    assert not (tmp_path / "tables").exists()
    assert "Zusammenfassung: 3 Bild(er), 1 Tabelle(n) uebersprungen" in out


def test_two_groups_with_the_same_league_text_do_not_overwrite_each_other(setup, tmp_path, monkeypatch):
    other = [raw_entry(1, 430043, "TV Oberwil BL I", CLUB), raw_entry(2, 77, "UHC Other")]
    monkeypatch.setitem(TABLES, 430043, (hdr("Junioren D Regional"), other))
    out = run()
    folder = tmp_path / "tables" / "2026"
    assert (folder / "junioren-d-regional.png").is_file() and (folder / "junioren-d-regional-2.png").is_file()
    assert "Zusammenfassung: 4 Bild(er)" in out


def test_a_table_that_cannot_fit_is_reported_not_cut_off(setup, tmp_path, monkeypatch):
    monkeypatch.setitem(TABLES, 431471, (hdr("Herren Aktive GF 4. Liga"), [raw_entry(1, 9, "X" * 400), raw_entry(2, 431471, "TV Oberwil BL", CLUB)]))
    out = run()
    assert "UEBERSPRUNGEN: Herren Aktive GF 4. Liga" in out and "passt nicht auf das Bild" in out
    assert not (tmp_path / "tables" / "2026" / "herren-aktive-gf-4-liga.png").exists()


def test_nothing_to_do_says_so(setup, monkeypatch):
    monkeypatch.setattr(cli, "get_teams", lambda client, cfg: [])
    assert "Keine Tabellen erzeugt." in run()


# --- additions for the web app: progress lines, uneven games, replacing old images ---


def test_progress_lines_for_the_web_app_progress_bar(setup):
    out = run()
    fetched = [line for line in out.splitlines() if line.startswith("[progress] Tabelle ")]
    assert fetched[0] == "[progress] Tabelle 1/5 geladen" and fetched[-1] == "[progress] Tabelle 5/5 geladen"  # 5 non-excluded teams
    created = [line for line in out.splitlines() if line.startswith("[progress] Bild ")]
    assert created == ["[progress] Bild 1/3 erstellt", "[progress] Bild 2/3 erstellt", "[progress] Bild 3/3 erstellt"]


def test_the_title_addition_is_logged_for_the_summary(setup):
    assert "Titel-Zusatz: keiner" in run().splitlines()
    assert "Titel-Zusatz: Winterpause" in run("--label", "Winterpause").splitlines()


def test_uneven_games_give_a_note_but_block_nothing(setup, tmp_path, monkeypatch):
    uneven = [raw_entry(1, 9, "UHC Foo", games=5), raw_entry(2, 431471, "TV Oberwil BL", CLUB, games=6)]
    monkeypatch.setitem(TABLES, 431471, (hdr("Herren Aktive GF 4. Liga"), uneven))
    out = run()
    assert "Hinweis: Ungleiche Spielzahl: Herren (laufender Spieltag?)" in out.splitlines()
    assert (tmp_path / "tables" / "2026" / "herren-aktive-gf-4-liga.png").is_file()  # still generated


def test_equal_games_give_no_note(setup):
    assert "Ungleiche Spielzahl" not in run()


def test_the_note_lists_every_tvo_team_of_every_uneven_table(setup, monkeypatch):
    d_uneven = [raw_entry(1, 430043, "TV Oberwil BL I", CLUB, games=8), raw_entry(2, 428478, "TV Oberwil BL II", CLUB, games=7)]
    monkeypatch.setitem(TABLES, 428478, (hdr("Junioren D Regional"), d_uneven))
    monkeypatch.setitem(TABLES, 430043, (hdr("Junioren D Regional"), d_uneven))
    uneven = [raw_entry(1, 9, "UHC Foo", games=5), raw_entry(2, 431471, "TV Oberwil BL", CLUB, games=6)]
    monkeypatch.setitem(TABLES, 431471, (hdr("Herren Aktive GF 4. Liga"), uneven))
    out = run()
    assert "Hinweis: Ungleiche Spielzahl: D Weiss, D Rot, Herren (laufender Spieltag?)" in out.splitlines()


def test_a_new_run_replaces_the_old_images_of_the_season(setup, tmp_path):
    folder = tmp_path / "tables" / "2026"
    folder.mkdir(parents=True)
    (folder / "gruppe-gibt-es-nicht-mehr.png").write_bytes(b"old")
    (folder / "junioren-d-regional.png").write_bytes(b"old")  # same name: overwritten, not duplicated
    (folder / "notiz.txt").write_text("bleibt")
    other_season = tmp_path / "tables" / "2025"
    other_season.mkdir()
    (other_season / "alt.png").write_bytes(b"other season")
    out = run()
    assert "Entfernt (veraltet): gruppe-gibt-es-nicht-mehr.png" in out
    assert sorted(p.name for p in folder.glob("*.png")) == [
        "herren-aktive-gf-4-liga.png", "junioren-d-regional.png", "juniorinnen-zuerich-u17-b.png",
    ]
    assert (folder / "junioren-d-regional.png").read_bytes() != b"old"
    assert (folder / "notiz.txt").exists() and (other_season / "alt.png").exists()  # nothing else is touched


def test_running_twice_gives_no_duplicates(setup, tmp_path):
    run()
    first = sorted(p.name for p in (tmp_path / "tables" / "2026").glob("*.png"))
    run("--label", "Winterpause")
    assert sorted(p.name for p in (tmp_path / "tables" / "2026").glob("*.png")) == first


def test_nothing_is_deleted_when_a_run_produces_no_images(setup, tmp_path, monkeypatch):
    folder = tmp_path / "tables" / "2026"
    folder.mkdir(parents=True)
    (folder / "behalten.png").write_bytes(b"keep")
    monkeypatch.setattr(cli, "get_teams", lambda client, cfg: [TEAMS[3]])  # only the team without a table (404)
    out = run()
    assert "Keine Tabellen erzeugt." in out
    assert (folder / "behalten.png").exists()


def test_a_dry_run_deletes_nothing(setup, tmp_path):
    folder = tmp_path / "tables" / "2026"
    folder.mkdir(parents=True)
    (folder / "alt.png").write_bytes(b"old")
    run("--dry-run")
    assert (folder / "alt.png").exists()
