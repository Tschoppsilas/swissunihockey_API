from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable

import requests

GRAPH_BASE = "https://graph.instagram.com/v23.0"
TIMEOUT_SECONDS = 20
CONTAINER_POLL_INTERVAL = 2.0
CONTAINER_POLL_MAX_SECONDS = 90

TOKEN_HINT = (
    "Der Instagram-Token ist abgelaufen oder ungültig. Bitte einen neuen Token generieren "
    "und bei Render als INSTAGRAM_ACCESS_TOKEN eintragen."
)
RATE_LIMIT_CODES = {4, 17, 32, 613}
PUBLISH_LIMIT_SUBCODE = 2207042


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


def _describe_error(status_code: int, payload: object) -> str:
    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    code = error.get("code")
    subcode = error.get("error_subcode")
    message = error.get("message") or f"HTTP {status_code}"
    if code == 190 or status_code == 401:
        return TOKEN_HINT
    if subcode == PUBLISH_LIMIT_SUBCODE or code in RATE_LIMIT_CODES:
        return f"Instagram-Limit erreicht (zu viele Anfragen/Posts) - bitte später erneut versuchen. ({message})"
    return f"Instagram hat die Anfrage abgelehnt: {message}"


def _call(method: str, url: str, creds: InstagramCredentials, **kwargs) -> dict:
    """One Graph API call. The token goes in a header so it can never end up in a URL
    or in an error message."""
    headers = {"Authorization": f"Bearer {creds.access_token}"}
    try:
        if method == "GET":
            response = requests.get(url, params=kwargs.get("params"), headers=headers, timeout=TIMEOUT_SECONDS)
        else:
            response = requests.post(url, data=kwargs.get("data"), headers=headers, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise InstagramError(f"Netzwerkfehler beim Kontaktieren von Instagram: {type(exc).__name__}") from None

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if response.status_code != 200 or (isinstance(payload, dict) and "error" in payload):
        raise InstagramError(_describe_error(response.status_code, payload))
    return payload


def check_connection() -> dict:
    """Read-only connection test: fetches the account's username, nothing is posted."""
    creds = load_credentials()
    payload = _call(
        "GET", f"{GRAPH_BASE}/{creds.user_id}", creds, params={"fields": "username,name,account_type"}
    )
    if not payload.get("username"):
        raise InstagramError("Antwort von Instagram enthielt keinen Konto-Namen.")
    return payload


def publish_story(
    image_url: str,
    on_stage: Callable[[str], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Publishes ONE image as an Instagram story: create container, wait until Instagram
    has fetched/processed the image (FINISHED), then media_publish. Returns
    {"media_id", "permalink"}. Deliberately never retries the publish step on its own -
    a retry after an ambiguous failure could post the same story twice."""
    creds = load_credentials()

    def stage(name: str) -> None:
        if on_stage:
            on_stage(name)

    stage("container")
    container = _call(
        "POST",
        f"{GRAPH_BASE}/{creds.user_id}/media",
        creds,
        data={"image_url": image_url, "media_type": "STORIES"},
    )
    container_id = container.get("id")
    if not container_id:
        raise InstagramError("Instagram hat keine Container-ID zurückgegeben.")

    stage("processing")
    waited = 0.0
    while True:
        status = _call("GET", f"{GRAPH_BASE}/{container_id}", creds, params={"fields": "status_code,status"})
        code = status.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            detail = status.get("status") or code
            raise InstagramError(f"Instagram konnte das Bild nicht verarbeiten: {detail}")
        if waited >= CONTAINER_POLL_MAX_SECONDS:
            raise InstagramError("Instagram hat das Bild nicht rechtzeitig verarbeitet (Zeitüberschreitung).")
        sleep(CONTAINER_POLL_INTERVAL)
        waited += CONTAINER_POLL_INTERVAL

    stage("publishing")
    published = _call(
        "POST", f"{GRAPH_BASE}/{creds.user_id}/media_publish", creds, data={"creation_id": container_id}
    )
    media_id = published.get("id")
    if not media_id:
        raise InstagramError("Instagram hat keine media_id zurückgegeben.")

    permalink = None
    try:
        permalink = _call("GET", f"{GRAPH_BASE}/{media_id}", creds, params={"fields": "permalink"}).get(
            "permalink"
        )
    except InstagramError:
        pass
    return {"media_id": media_id, "permalink": permalink}
