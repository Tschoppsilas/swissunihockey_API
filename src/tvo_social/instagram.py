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
CAROUSEL_MIN_ITEMS = 2
CAROUSEL_MAX_ITEMS = 10
CAPTION_MAX_CHARS = 2200

TOKEN_HINT = (
    "Der Instagram-Token ist abgelaufen oder ungültig. Bitte einen neuen Token generieren "
    "und bei Render als INSTAGRAM_ACCESS_TOKEN eintragen."
)
RATE_LIMIT_CODES = {4, 17, 32, 613}
PUBLISH_LIMIT_SUBCODE = 2207042

# on_stage(stage, current, total): stage is one of "child" (carousel image
# current/total), "container", "processing", "publishing".
StageCallback = Callable[..., None]


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


def _create_container(creds: InstagramCredentials, data: dict) -> str:
    container = _call("POST", f"{GRAPH_BASE}/{creds.user_id}/media", creds, data=data)
    container_id = container.get("id")
    if not container_id:
        raise InstagramError("Instagram hat keine Container-ID zurückgegeben.")
    return container_id


def _wait_until_finished(creds: InstagramCredentials, container_id: str, sleep: Callable[[float], None]) -> None:
    waited = 0.0
    while True:
        status = _call("GET", f"{GRAPH_BASE}/{container_id}", creds, params={"fields": "status_code,status"})
        code = status.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            detail = status.get("status") or code
            raise InstagramError(f"Instagram konnte das Bild nicht verarbeiten: {detail}")
        if waited >= CONTAINER_POLL_MAX_SECONDS:
            raise InstagramError("Instagram hat das Bild nicht rechtzeitig verarbeitet (Zeitüberschreitung).")
        sleep(CONTAINER_POLL_INTERVAL)
        waited += CONTAINER_POLL_INTERVAL


def _publish_container(creds: InstagramCredentials, container_id: str) -> dict:
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


def publish_story(
    image_url: str,
    on_stage: StageCallback | None = None,
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
    container_id = _create_container(creds, {"image_url": image_url, "media_type": "STORIES"})
    stage("processing")
    _wait_until_finished(creds, container_id, sleep)
    stage("publishing")
    return _publish_container(creds, container_id)


def publish_feed(
    image_urls: list[str],
    caption: str,
    on_stage: StageCallback | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Publishes a feed post: one image -> single post, 2-10 -> carousel in the given
    order, with one shared caption. Same safety rules as publish_story: nothing is
    published unless every container reached FINISHED, and the publish step is never
    retried automatically."""
    if not image_urls:
        raise InstagramError("Keine Bilder zum Posten.")
    if len(image_urls) > CAROUSEL_MAX_ITEMS:
        raise InstagramError(f"Ein Karussell erlaubt maximal {CAROUSEL_MAX_ITEMS} Bilder.")
    if len(caption) > CAPTION_MAX_CHARS:
        raise InstagramError(f"Der Text ist zu lang ({len(caption)} von {CAPTION_MAX_CHARS} Zeichen).")
    creds = load_credentials()

    def stage(name: str, current: int = 0, total: int = 0) -> None:
        if on_stage:
            on_stage(name, current, total)

    if len(image_urls) == 1:
        stage("container")
        data = {"image_url": image_urls[0], "media_type": "IMAGE"}
        if caption:
            data["caption"] = caption
        container_id = _create_container(creds, data)
    else:
        child_ids = []
        total = len(image_urls)
        for index, url in enumerate(image_urls, start=1):
            stage("child", index, total)
            child_id = _create_container(creds, {"image_url": url, "is_carousel_item": "true"})
            _wait_until_finished(creds, child_id, sleep)
            child_ids.append(child_id)
        stage("container")
        data = {"media_type": "CAROUSEL", "children": ",".join(child_ids)}
        if caption:
            data["caption"] = caption
        container_id = _create_container(creds, data)

    stage("processing")
    _wait_until_finished(creds, container_id, sleep)
    stage("publishing")
    return _publish_container(creds, container_id)
