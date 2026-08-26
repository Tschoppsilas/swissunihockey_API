from __future__ import annotations

import json
from typing import Any, Literal

import requests


class ApiClient:
    """Thin transport layer around the swissunihockey REST v1.0 API.

    Isolated on purpose: if the undocumented no-key access ever breaks
    (real apikey enforced, or v1.0 retired in favor of v2), only this
    file needs to change.
    """

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._cache: dict[str, Any] = {}
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any | None:
        params = params or {}
        cache_key = f"{path}?{sorted(params.items())}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        url = f"{self.base_url}/{path.lstrip('/')}"
        response = self._session.get(url, params=params, timeout=self.timeout)
        if response.status_code == 404:
            # The API returns 404 (instead of an empty list) when a team
            # currently has no games matching the requested status.
            self._cache[cache_key] = None
            return None
        response.raise_for_status()
        # Server bug: non-ASCII characters (ü/ö/ä) are emitted as raw
        # Windows-1252 bytes despite the declared application/json content
        # type, which is supposed to be UTF-8. Decode accordingly instead
        # of trusting response.json()/.encoding.
        data = json.loads(response.content.decode("cp1252"))
        self._cache[cache_key] = data
        return data

    @staticmethod
    def _as_list(value: Any) -> list[dict]:
        # The API's XML-to-JSON conversion collapses a single child element
        # into a bare dict instead of a one-item list.
        if value is None:
            return []
        if isinstance(value, dict):
            return [value]
        return value

    def get_club_teams(self, club_id: int) -> list[dict]:
        data = self._get(f"/clubs/{club_id}/teams")
        if data is None:
            return []
        return self._as_list(data.get("teams", {}).get("team", []))

    def get_team_games(
        self,
        team_id: int,
        status: Literal["planned", "played"],
        limit: int = 20,
        order: str = "ASC",
    ) -> list[dict]:
        data = self._get(
            f"/teams/{team_id}/games",
            params={"status": status, "limit": limit, "order": order},
        )
        if data is None:
            return []
        return self._as_list(data.get("games", {}).get("game", []))
