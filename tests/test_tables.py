import pytest

from tvo_social.api_client import ApiClient
from tvo_social.models import LeagueTable, TableEntry, Team
from tvo_social.tables import ascii_text, build_rows, collect_tables, excluded_by, slugify

CLUB = 696


def raw_entry(place, team_id, name, club=1, games=8, wins=4, ties=1, defeats=3, gf=30, ga=25, points=13, wo=0, do=0):
    return {
        "place": place, "teamid": team_id, "clubid": club, "teamname": name, "games": games, "wins": wins,
        "ties": ties, "defeats": defeats, "goals-scored": gf, "goals-received": ga, "points": points,
        "wins-overtime": wo, "defeats-overtime": do, "games-without-score": 0,
        "points_quotient": 1.5, "wins_quotient": 0.5,
    }


def header(league="Junioren D Regional", season=2026):
    return {"season": season, "leaguetext": league, "leaguetype": "Meisterschaft"}


D_TABLE = [
    raw_entry(1, 430043, "TV Oberwil BL I", CLUB),
    raw_entry(2, 428478, "TV Oberwil BL II", CLUB),
    raw_entry(3, 1, "UHC Basel United I"),
    raw_entry(4, 430201, "TV Oberwil BL III", CLUB),
]
HERREN_TABLE = [raw_entry(1, 7, "UHC Lenzburg"), raw_entry(2, 431471, "TV Oberwil BL", CLUB)]
E_TABLE = [raw_entry(1, 429806, "TV Oberwil BL I", CLUB), raw_entry(2, 9, "UHC Foo")]

TEAMS = [
    Team(428478, "TV Oberwil BL", "Junioren D Regional", 344),
    Team(430201, "TV Oberwil BL", "Junioren D Regional", 344),
    Team(430043, "TV Oberwil BL", "Junioren D Regional", 344),
    Team(431471, "TV Oberwil BL", "Herren Aktive GF 4. Liga", 116),
    Team(429806, "TV Oberwil BL", "Junioren E Regional", 354),
    Team(432099, "TV Oberwil BL", "Junioren E Regional", 354),
]
LABELS = {430043: "D Rot", 428478: "D Weiss", 430201: "D Blau", 429806: "E Rot", 431471: "Herren"}


class FakeClient:
    def __init__(self, tables):
        self.tables = tables  # team id -> (header, entries) or None
        self.calls = []

    def get_team_table(self, team_id, season=None):
        self.calls.append((team_id, season))
        return self.tables.get(team_id)


def fake_tables():
    d = (header(), D_TABLE)
    return {
        428478: d, 430201: d, 430043: d,
        431471: (header("Herren Aktive GF 4. Liga"), HERREN_TABLE),
        429806: (header("Junioren E Regional"), E_TABLE),
    }


# --- text helpers ---


def test_ascii_text_and_slugify_never_leave_cp1252_trouble():
    assert ascii_text("Zürich Füllinsdorf · Ä ß") == "Zuerich Fuellinsdorf ? Ae ss"
    assert slugify("Juniorinnen Zürich U17 B") == "juniorinnen-zuerich-u17-b"
    assert slugify("Herren Aktive GF 4. Liga") == "herren-aktive-gf-4-liga"
    assert slugify("???") == "tabelle"


# --- exclusion list ---


def test_exclusion_matches_the_start_of_the_category_case_insensitively():
    assert excluded_by("Junioren E Regional", ["Junioren E"]) == "Junioren E"
    assert excluded_by("junioren e regional", ["Junioren E"]) == "Junioren E"
    assert excluded_by("Junioren D Regional", ["Junioren E"]) is None
    assert excluded_by("Junioren U14 B", ["Junioren E"]) is None
    assert excluded_by("Junioren E Regional", []) is None
    assert excluded_by("Junioren E Regional", ["", "  "]) is None


def test_excluded_categories_are_not_fetched_and_logged_once():
    client, log = FakeClient(fake_tables()), []
    groups, skipped = collect_tables(client, TEAMS, LABELS, ("Junioren E",), None, log.append)
    assert [c for c in log if "ausgeschlossen" in c] == ["Junioren E: ausgeschlossen (Konfiguration)"]
    assert not any(team_id in (429806, 432099) for team_id, _ in client.calls)
    assert skipped == []
    assert [g.table.league_text for g in groups] == ["Junioren D Regional", "Herren Aktive GF 4. Liga"]


def test_removing_the_exclusion_switches_the_category_on_again():
    client, log = FakeClient(fake_tables()), []
    groups, _ = collect_tables(client, TEAMS, LABELS, (), None, log.append)
    assert "Junioren E Regional" in [g.table.league_text for g in groups]
    assert not any("ausgeschlossen" in c for c in log)


# --- one image per distinct table ---


def test_teams_with_the_same_table_share_one_group():
    client, log = FakeClient(fake_tables()), []
    groups, _ = collect_tables(client, TEAMS, LABELS, ("Junioren E",), None, log.append)
    d_group = groups[0]
    assert {t.id for t in d_group.tvo_teams} == {428478, 430201, 430043}
    assert len(groups) == 2
    assert sum("gleiche Tabelle" in line for line in log) == 2


def test_different_seasons_or_groups_are_not_merged():
    other = [raw_entry(1, 430043, "TV Oberwil BL I", CLUB), raw_entry(2, 99, "UHC Other")]
    tables = {428478: (header(), D_TABLE), 430043: (header(), other)}
    teams = [t for t in TEAMS if t.id in (428478, 430043)]
    groups, _ = collect_tables(FakeClient(tables), teams, LABELS, (), 2025, lambda _: None)
    assert len(groups) == 2


def test_the_season_is_passed_through_to_the_team_endpoint():
    client = FakeClient(fake_tables())
    collect_tables(client, TEAMS[:1], LABELS, (), 2025, lambda _: None)
    assert client.calls == [(428478, 2025)]


# --- skipping with a reason, never an empty image ---


def test_missing_and_empty_tables_are_skipped_with_a_reason():
    empty = (header(), [raw_entry(1, 431471, "TV Oberwil BL", CLUB, games=0, wins=0, ties=0, defeats=0, gf=0, ga=0, points=0)])
    no_entries = (header(), [])
    teams = [
        Team(1, "TV Oberwil BL", "Junioren U18 C", 183),
        Team(431471, "TV Oberwil BL", "Herren Aktive GF 4. Liga", 116),
        Team(3, "TV Oberwil BL", "Damen Aktive KF 3. Liga", 225),
    ]
    tables = {1: None, 431471: empty, 3: no_entries}
    groups, skipped = collect_tables(FakeClient(tables), teams, {1: "U18"}, (), None, lambda _: None)
    assert groups == []
    assert [(s.label, s.reason) for s in skipped] == [
        ("U18", "keine Tabelle (404)"),
        ("Herren Aktive GF 4. Liga", "Tabelle leer (noch keine Spiele)"),
        ("Damen Aktive KF 3. Liga", "Tabelle leer (noch keine Spiele)"),
    ]


# --- naming of the TVO teams ---


def table_of(entries):
    return LeagueTable.from_api(header(), entries)


def test_a_single_tvo_team_is_called_tv_oberwil_without_label():
    rows = build_rows(table_of(HERREN_TABLE), LABELS, CLUB)
    assert [r.name for r in rows] == ["UHC Lenzburg", "TV Oberwil"]
    assert [r.is_tvo for r in rows] == [False, True]  # the label "Herren" is deliberately not used


def test_several_tvo_teams_in_one_table_get_tvo_plus_label():
    rows = build_rows(table_of(D_TABLE), LABELS, CLUB)
    assert [r.name for r in rows] == ["TVO D Rot", "TVO D Weiss", "UHC Basel United I", "TVO D Blau"]
    assert [r.is_tvo for r in rows] == [True, True, False, True]


def test_the_rule_is_general_not_tied_to_the_d_category():
    entries = [raw_entry(1, 10, "TV Oberwil BL I", CLUB), raw_entry(2, 11, "TV Oberwil BL II", CLUB), raw_entry(3, 5, "X")]
    rows = build_rows(table_of(entries), {10: "Rot", 11: "Weiss"}, CLUB)
    assert [r.name for r in rows] == ["TVO Rot", "TVO Weiss", "X"]


def test_without_a_label_the_roman_numeral_is_used():
    entries = [raw_entry(1, 10, "TV Oberwil BL I", CLUB), raw_entry(2, 11, "TV Oberwil BL II", CLUB)]
    rows = build_rows(table_of(entries), {}, CLUB)
    assert [r.name for r in rows] == ["TVO I", "TVO II"]


def test_other_clubs_keep_their_names_untouched():
    rows = build_rows(table_of(D_TABLE), LABELS, CLUB)
    assert rows[2].name == "UHC Basel United I"


# --- model ---


def test_table_is_ordered_by_the_api_place_and_derives_the_goal_difference():
    shuffled = [raw_entry(3, 3, "C"), raw_entry(1, 1, "A", gf=10, ga=4), raw_entry(2, 2, "B")]
    table = table_of(shuffled)
    assert [e.place for e in table.entries] == [1, 2, 3]
    assert table.entries[0].goal_difference == 6


def test_overtime_columns_only_when_some_team_has_a_value():
    assert not table_of([raw_entry(1, 1, "A"), raw_entry(2, 2, "B")]).has_overtime_columns
    assert table_of([raw_entry(1, 1, "A"), raw_entry(2, 2, "B", wo=1)]).has_overtime_columns
    assert table_of([raw_entry(1, 1, "A", do=2), raw_entry(2, 2, "B")]).has_overtime_columns


# --- API client ---


def test_client_returns_none_on_404_and_collapses_a_single_entry(monkeypatch):
    client = ApiClient("http://x")
    seen = {}

    def fake_get(path, params=None):
        seen["call"] = (path, params)
        return {"table": {"season": 2026, "leaguetext": "L", "entry": raw_entry(1, 1, "Solo")}}

    monkeypatch.setattr(client, "_get", fake_get)
    table, entries = client.get_team_table(5, 2025)
    assert seen["call"] == ("/teams/5/table", {"season": 2025})
    assert len(entries) == 1 and entries[0]["teamname"] == "Solo"
    client.get_team_table(5)
    assert seen["call"] == ("/teams/5/table", None)

    monkeypatch.setattr(client, "_get", lambda path, params=None: None)
    assert client.get_team_table(5) is None


def test_table_entry_from_api_reads_every_column():
    entry = TableEntry.from_api(raw_entry(2, 7, "Foo", 3, 9, 5, 1, 3, 31, 20, 16, wo=1, do=2))
    assert (entry.place, entry.team_id, entry.club_id, entry.name, entry.games) == (2, 7, 3, "Foo", 9)
    assert (entry.wins, entry.wins_overtime, entry.ties, entry.defeats_overtime, entry.defeats) == (5, 1, 1, 2, 3)
    assert (entry.goals_for, entry.goals_against, entry.points, entry.goal_difference) == (31, 20, 16, 11)
