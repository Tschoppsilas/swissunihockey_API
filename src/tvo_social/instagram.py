from __future__ import annotations

import os
from dataclasses import dataclass

import requests

GRAPH_BASE = "https://graph.instagram.com/v23.0"
TIMEOUT_SECONDS = 15


class InstagramError(Exception):
    pass


@dataclass(frozen=True)
class InstagramCredentials:
    access_token: str
    user_id: str


def load_credentials() -> InstagramCredentials:
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
    user_id = os.environ.get("INSTAGRAM_USER_ID", "").strip()
    missing = [
        name
        for name, value in (("INSTAGRAM_ACCESS_TOKEN", token), ("INSTAGRAM_USER_ID", user_id))
        if not value
    ]
    if missing:
        raise InstagramError("Umgebungsvariable(n) nicht gesetzt: " + ", ".join(missing))
    return InstagramCredentials(access_token=token, user_id=user_id)


def check_connection() -> dict:
    """Read-only connection test: fetches the account's username, nothing is posted.
    The token is sent as a header so it can never end up in a URL or an error message."""
    creds = load_credentials()
    try:
        response = requests.get(
            f"{GRAPH_BASE}/{creds.user_id}",
            params={"fields": "username,name,account_type"},
            headers={"Authorization": f"Bearer {creds.access_token}"},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise InstagramError(f"Netzwerkfehler beim Kontaktieren von Instagram: {type(exc).__name__}") from None

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if response.status_code != 200 or "error" in payload:
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        message = error.get("message") or f"HTTP {response.status_code}"
        raise InstagramError(f"Instagram hat die Anfrage abgelehnt: {message}")

    if not payload.get("username"):
        raise InstagramError("Antwort von Instagram enthielt keinen Konto-Namen.")
    return payload
