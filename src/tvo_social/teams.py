from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from .api_client import ApiClient
from .config import Config
from .models import Team

CACHE_FILENAME = "teams.json"


def _cache_path(cfg: Config) -> Path:
    return cfg.cache_dir / CACHE_FILENAME


def _read_cache(cfg: Config) -> tuple[list[Team], datetime] | None:
    path = _cache_path(cfg)
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    fetched_at = datetime.fromisoformat(raw["fetched_at"])
    teams = [Team(**t) for t in raw["teams"]]
    return teams, fetched_at


def _write_cache(cfg: Config, teams: list[Team]) -> None:
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now().isoformat(),
        "teams": [
            {
                "id": t.id,
                "name": t.name,
                "category": t.category,
                "league_code": t.league_code,
            }
            for t in teams
        ],
    }
    with _cache_path(cfg).open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def refresh_team_cache(client: ApiClient, cfg: Config) -> list[Team]:
    raw_teams = client.get_club_teams(cfg.club_id)
    teams = [Team.from_api(t) for t in raw_teams]
    _write_cache(cfg, teams)
    return teams


def get_teams(client: ApiClient, cfg: Config, force_refresh: bool = False) -> list[Team]:
    if not force_refresh:
        cached = _read_cache(cfg)
        if cached is not None:
            teams, fetched_at = cached
            staleness = timedelta(days=cfg.team_cache_staleness_days)
            if datetime.now() - fetched_at < staleness:
                return teams

    return refresh_team_cache(client, cfg)
