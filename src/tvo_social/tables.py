from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable

from .api_client import ApiClient
from .models import LeagueTable, TableEntry, Team

TVO_NAME = "TV Oberwil"

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})


def ascii_text(text: str) -> str:
    """Console-safe text: Windows consoles (cp1252) must never see a character
    they cannot encode, so every log line goes through this."""
    folded = unicodedata.normalize("NFKD", text.translate(_UMLAUTS))
    return folded.encode("ascii", "replace").decode("ascii")


def slugify(text: str) -> str:
    """'Junioren D Regional' -> 'junioren-d-regional' (ASCII, for file names)."""
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text(text).lower()).strip("-")
    return slug or "tabelle"


@dataclass
class TableGroup:
    """One table image: a league group, with every TVO team that plays in it
    (several TVO teams of the same group share one image)."""

    table: LeagueTable
    tvo_teams: list[Team] = field(default_factory=list)


@dataclass(frozen=True)
class SkippedTable:
    label: str
    category: str
    reason: str


@dataclass(frozen=True)
class TableRow:
    entry: TableEntry
    name: str  # display name, as it appears in the image
    is_tvo: bool


def excluded_by(category: str, patterns: tuple[str, ...] | list[str]) -> str | None:
    """The config entry that excludes this category (start of the API category
    text, case-insensitive), or None."""
    lowered = category.lower()
    for pattern in patterns:
        if pattern.strip() and lowered.startswith(pattern.strip().lower()):
            return pattern
    return None


def collect_tables(
    client: ApiClient,
    teams: list[Team],
    labels: dict[int, str],
    exclude_categories: tuple[str, ...] | list[str],
    season: int | None,
    log: Callable[[str], None],
) -> tuple[list[TableGroup], list[SkippedTable]]:
    """One TableGroup per distinct table. Always asks the team endpoint (league
    codes and group numbers change every season); two teams whose tables hold
    the same teams share one image. A missing (404) or empty table is skipped
    with a reason instead of producing an empty image."""
    groups: dict[tuple[int, str, frozenset[int]], TableGroup] = {}
    skipped: list[SkippedTable] = []
    announced: set[str] = set()

    for team in teams:
        label = labels.get(team.id, team.category)
        pattern = excluded_by(team.category, exclude_categories)
        if pattern is not None:
            if pattern not in announced:
                announced.add(pattern)
                log(f"{pattern}: ausgeschlossen (Konfiguration)")
            continue

        result = client.get_team_table(team.id, season)
        if result is None:
            skipped.append(SkippedTable(label, team.category, "keine Tabelle (404)"))
            continue
        header, raw_entries = result
        table = LeagueTable.from_api(header, raw_entries)
        if not table.entries or all(e.games == 0 for e in table.entries):
            skipped.append(SkippedTable(label, team.category, "Tabelle leer (noch keine Spiele)"))
            continue

        key = (table.season, table.league_text, table.team_ids)
        if key in groups:
            groups[key].tvo_teams.append(team)
            log(f"{label} ({team.category}): gleiche Tabelle wie {labels.get(groups[key].tvo_teams[0].id, groups[key].tvo_teams[0].category)} - zusammengefasst")
        else:
            groups[key] = TableGroup(table=table, tvo_teams=[team])

    return list(groups.values()), skipped


def _variant_suffix(raw_name: str) -> str:
    match = re.match(r"^TV Oberwil(?: BL)?\s*(.*)$", raw_name.strip())
    return match.group(1).strip() if match else raw_name.strip()


def build_rows(table: LeagueTable, labels: dict[int, str], club_id: int) -> list[TableRow]:
    """Display rows for the image. The TVO team is "TV Oberwil" when it is the
    only one in this table; when several TVO teams share the table, each is
    "TVO" plus its label from team_labels.yaml (e.g. "TVO D Rot")."""
    tvo_count = sum(1 for e in table.entries if e.club_id == club_id)
    rows = []
    for entry in table.entries:
        if entry.club_id != club_id:
            rows.append(TableRow(entry, entry.name, False))
        elif tvo_count > 1:
            label = labels.get(entry.team_id) or _variant_suffix(entry.name)
            rows.append(TableRow(entry, f"TVO {label}".strip(), True))
        else:
            rows.append(TableRow(entry, TVO_NAME, True))
    return rows
