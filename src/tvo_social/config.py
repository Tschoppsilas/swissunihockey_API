from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_TEAM_LABELS_PATH = Path("team_labels.yaml")


@dataclass
class Config:
    club_id: int = 696
    api_base: str = "https://api.swissunihockey.ch/rest/v1.0"
    output_dir: Path = Path("output")
    cache_dir: Path = Path("cache")
    team_cache_staleness_days: int = 7
    home_venue: str = "Thomasgarten (Oberwil BL)"


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    if not path.exists():
        return Config()

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return Config(
        club_id=raw.get("club_id", Config.club_id),
        api_base=raw.get("api_base", Config.api_base),
        output_dir=Path(raw.get("output_dir", "output")),
        cache_dir=Path(raw.get("cache_dir", "cache")),
        team_cache_staleness_days=raw.get(
            "team_cache_staleness_days", Config.team_cache_staleness_days
        ),
        home_venue=raw.get("home_venue", Config.home_venue),
    )


def load_team_labels(path: Path = DEFAULT_TEAM_LABELS_PATH) -> dict[int, str]:
    """team_id -> display label overrides (e.g. distinguishing jersey colors
    for multiple TVO teams in the same league category)."""
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return {int(k): v for k, v in raw.items()}
