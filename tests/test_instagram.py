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
