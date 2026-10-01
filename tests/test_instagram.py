import pytest
import requests

from tvo_social import instagram
from tvo_social.instagram import InstagramError, check_connection


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "SECRET-TOKEN")
    monkeypatch.setenv("INSTAGRAM_USER_ID", "12345")


def test_missing_env_vars(monkeypatch):
    monkeypatch.delenv("INSTAGRAM_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("INSTAGRAM_USER_ID", raising=False)
    with pytest.raises(InstagramError, match="INSTAGRAM_ACCESS_TOKEN.*INSTAGRAM_USER_ID"):
        check_connection()


def test_success_sends_token_as_header_only(creds, monkeypatch):
    seen = {}

    def fake_get(url, params, headers, timeout):
        seen.update(url=url, params=params, headers=headers)
        return FakeResponse(200, {"username": "tvoberwil", "account_type": "BUSINESS", "id": "12345"})

    monkeypatch.setattr(instagram.requests, "get", fake_get)
    info = check_connection()
    assert info["username"] == "tvoberwil"
    assert seen["url"].endswith("/12345")
    assert seen["headers"]["Authorization"] == "Bearer SECRET-TOKEN"
    assert "SECRET-TOKEN" not in seen["url"]
    assert "access_token" not in seen["params"]


def test_api_error_message_surfaced_without_token(creds, monkeypatch):
    monkeypatch.setattr(
        instagram.requests,
        "get",
        lambda *a, **k: FakeResponse(400, {"error": {"message": "Invalid OAuth access token"}}),
    )
    with pytest.raises(InstagramError, match="Invalid OAuth access token") as exc:
        check_connection()
    assert "SECRET-TOKEN" not in str(exc.value)


def test_network_error_does_not_leak_token(creds, monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("failed for Bearer SECRET-TOKEN")

    monkeypatch.setattr(instagram.requests, "get", boom)
    with pytest.raises(InstagramError) as exc:
        check_connection()
    assert "SECRET-TOKEN" not in str(exc.value)


class Recorder:
    """Fake Graph API: records calls, replays queued responses per (method, url-suffix)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def _answer(self, method, url, **kw):
        self.calls.append((method, url, kw))
        for (m, suffix), queue in self.routes.items():
            if m == method and url.endswith(suffix):
                return queue.pop(0) if len(queue) > 1 else queue[0]
        raise AssertionError(f"unexpected call {method} {url}")

    def get(self, url, params=None, headers=None, timeout=None):
        return self._answer("GET", url, params=params, headers=headers)

    def post(self, url, data=None, headers=None, timeout=None):
        return self._answer("POST", url, data=data, headers=headers)


def _install(monkeypatch, routes):
    rec = Recorder(routes)
    monkeypatch.setattr(instagram.requests, "get", rec.get)
    monkeypatch.setattr(instagram.requests, "post", rec.post)
    return rec


def test_publish_story_happy_path_waits_for_finished(creds, monkeypatch):
    rec = _install(
        monkeypatch,
        {
            ("POST", "/12345/media"): [FakeResponse(200, {"id": "C1"})],
            ("GET", "/C1"): [
                FakeResponse(200, {"status_code": "IN_PROGRESS"}),
                FakeResponse(200, {"status_code": "FINISHED"}),
            ],
            ("POST", "/12345/media_publish"): [FakeResponse(200, {"id": "M9"})],
            ("GET", "/M9"): [FakeResponse(200, {"permalink": "https://instagram.com/stories/x/1"})],
        },
    )
    stages, sleeps = [], []
    result = instagram.publish_story("https://x/p/t.jpg", on_stage=stages.append, sleep=sleeps.append)

    assert result == {"media_id": "M9", "permalink": "https://instagram.com/stories/x/1"}
    assert stages == ["container", "processing", "publishing"]
    assert len(sleeps) == 1
    assert rec.calls[0][2]["data"] == {"image_url": "https://x/p/t.jpg", "media_type": "STORIES"}
    publish = [c for c in rec.calls if c[1].endswith("media_publish")][0]
    assert publish[2]["data"] == {"creation_id": "C1"}
    assert all("SECRET-TOKEN" not in c[1] for c in rec.calls)


def test_publish_story_never_publishes_when_container_errors(creds, monkeypatch):
    rec = _install(
        monkeypatch,
        {
            ("POST", "/12345/media"): [FakeResponse(200, {"id": "C1"})],
            ("GET", "/C1"): [FakeResponse(200, {"status_code": "ERROR", "status": "bad image"})],
        },
    )
    with pytest.raises(InstagramError, match="bad image"):
        instagram.publish_story("https://x/p/t.jpg", sleep=lambda s: None)
    assert not any(c[1].endswith("media_publish") for c in rec.calls)


def test_publish_story_times_out_without_publishing(creds, monkeypatch):
    rec = _install(
        monkeypatch,
        {
            ("POST", "/12345/media"): [FakeResponse(200, {"id": "C1"})],
            ("GET", "/C1"): [FakeResponse(200, {"status_code": "IN_PROGRESS"})],
        },
    )
    with pytest.raises(InstagramError, match="Zeitüberschreitung"):
        instagram.publish_story("https://x/p/t.jpg", sleep=lambda s: None)
    assert not any(c[1].endswith("media_publish") for c in rec.calls)


def test_expired_token_gives_actionable_message(creds, monkeypatch):
    _install(
        monkeypatch,
        {("POST", "/12345/media"): [FakeResponse(400, {"error": {"code": 190, "message": "Error validating"}})]},
    )
    with pytest.raises(InstagramError, match="INSTAGRAM_ACCESS_TOKEN"):
        instagram.publish_story("https://x/p/t.jpg", sleep=lambda s: None)


def test_publish_limit_message(creds, monkeypatch):
    _install(
        monkeypatch,
        {
            ("POST", "/12345/media"): [FakeResponse(200, {"id": "C1"})],
            ("GET", "/C1"): [FakeResponse(200, {"status_code": "FINISHED"})],
            ("POST", "/12345/media_publish"): [
                FakeResponse(400, {"error": {"code": 9, "error_subcode": 2207042, "message": "limit"}})
            ],
        },
    )
    with pytest.raises(InstagramError, match="Limit erreicht"):
        instagram.publish_story("https://x/p/t.jpg", sleep=lambda s: None)
