from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

# The API doesn't leave gym.content empty/null when no venue is assigned -
# it sends a placeholder string instead (observed: "-", with gym.id -1).
# Normalizing here, once, at the parsing boundary means every downstream
# check (venue pill, missing-venue stamp, console report) that tests
# `not game.venue` just works, instead of each needing its own placeholder
# list.
_MISSING_VENUE_PLACEHOLDERS = {"-", "–", "—", "tbd", "n/a", "noch offen", "offen"}


def _normalize_venue(raw_venue: str) -> str:
    stripped = raw_venue.strip()
    if not stripped or stripped.lower() in _MISSING_VENUE_PLACEHOLDERS:
        return ""
    return raw_venue


@dataclass(frozen=True)
class Team:
    id: int
    name: str
    category: str
    league_code: int

    @classmethod
    def from_api(cls, raw: dict) -> "Team":
        return cls(
            id=raw["id"],
            name=raw["teamname"],
            category=raw["content"],
            league_code=raw["leaguecode"],
        )


@dataclass(frozen=True)
class Game:
    id: int
    date: date
    time: str | None
    home_team: str
    away_team: str
    home_team_id: int
    away_team_id: int
    venue: str
    league_text: str
    category_text: str
    played: bool
    goals_home: int | None
    goals_away: int | None
    overtime: bool = False
    penalty_shooting: bool = False
    forfait: bool = False
    canceled: bool = False

    @classmethod
    def from_api(cls, raw: dict) -> "Game":
        goals_home = raw.get("goalshome", -1)
        goals_away = raw.get("goalsaway", -1)
        return cls(
            id=raw["id"],
            date=datetime.strptime(raw["date"], "%d.%m.%Y").date(),
            time=raw.get("time") or None,
            home_team=raw["hometeamname"],
            away_team=raw["awayteamname"],
            home_team_id=raw["hometeamid"],
            away_team_id=raw["awayteamid"],
            venue=_normalize_venue((raw.get("gym") or {}).get("content", "")),
            league_text=raw.get("leaguetext", ""),
            category_text=raw.get("grouptext", ""),
            played=raw.get("played", False),
            goals_home=None if goals_home == -1 else goals_home,
            goals_away=None if goals_away == -1 else goals_away,
            overtime=raw.get("overtime", False),
            penalty_shooting=raw.get("penaltyshooting", False),
            forfait=raw.get("forfait", False),
            canceled=raw.get("canceled", False),
        )


@dataclass(frozen=True)
class TeamGame:
    """A Game annotated from the perspective of one specific TVO team.

    Built once we know which of the two sides is "us" (the team whose
    fixture list this game came from), so grouping/rendering never has to
    re-derive home/away perspective, opponent name, or which league-category
    label to show (which, for teams sharing a category, e.g. Junioren D
    Rot/Weiss/Blau, isn't recoverable from the game data alone).
    """

    game: Game
    category: str
    opponent: str
    our_goals: int | None
    opp_goals: int | None
    is_home: bool
    opponent_is_tvo: bool = False

    @property
    def date(self) -> date:
        return self.game.date

    def score_text(self) -> str:
        if self.game.canceled or self.our_goals is None or self.opp_goals is None:
            return "-:-"
        suffix = ""
        if self.game.penalty_shooting:
            suffix = " nP"
        elif self.game.overtime:
            suffix = " nV"
        return f"{self.our_goals}:{self.opp_goals}{suffix}"

    def result_kind(self) -> Literal["win", "loss", "draw", "unknown"]:
        if self.our_goals is None or self.opp_goals is None:
            return "unknown"
        if self.our_goals > self.opp_goals:
            return "win"
        if self.our_goals < self.opp_goals:
            return "loss"
        return "draw"
