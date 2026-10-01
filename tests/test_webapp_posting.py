import pytest
from fastapi import HTTPException
from PIL import Image

from tvo_social import webapp
from tvo_social.instagram import InstagramError

STORY_1 = "story/2026-W40/post_1of2.png"
STORY_2 = "story/2026-W40/post_2of2.png"
FEED_1 = "announcements/2026-W40/post_1of1.png"


class NoopThread:
    def __init__(self, target, args, daemon):
        pass

    def start(self):
        pass


@pytest.fixture
def output(tmp_path, monkeypatch):
    for rel in (STORY_1, STORY_2, FEED_1):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1080, 1920), "red").save(p)
    monkeypatch.setattr(webapp, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test/")
    monkeypatch.setattr(webapp.threading, "Thread", NoopThread)
    webapp.POST_JOB.update(running=False, done=False, results=[], error="")
    return tmp_path


def start(paths):
    return webapp.start_story_post(webapp.StoryPostRequest(paths=paths), None)


def test_public_image_is_jpeg_random_url_and_dropped(output):
    token = webapp._register_public_image(output / STORY_1)
    assert len(token) >= 40
    response = webapp.get_public_image(token)
    assert response.media_type == "image/jpeg"
    assert response.body[:3] == bytes([0xFF, 0xD8, 0xFF])
    webapp._drop_public_image(token)
    with pytest.raises(HTTPException) as exc:
        webapp.get_public_image(token)
    assert exc.value.status_code == 404


def test_public_image_expired_token_404(output, monkeypatch):
    token = webapp._register_public_image(output / STORY_1)
    monkeypatch.setattr(webapp.time, "time", lambda: 10**12)
    with pytest.raises(HTTPException):
        webapp.get_public_image(token)
    webapp._drop_public_image(token)


@pytest.mark.parametrize(
    "paths",
    [[], [FEED_1], ["story/../../etc/passwd"], ["story/missing.png"], [STORY_1, STORY_1]],
)
def test_start_rejects_bad_selection(output, paths):
    with pytest.raises(HTTPException) as exc:
        start(paths)
    assert exc.value.status_code in (400, 404)
    assert not webapp.POST_JOB["running"]


def test_start_rejects_second_job_while_running(output):
    assert start([STORY_1]) == {"started": True}
    with pytest.raises(HTTPException) as exc:
        start([STORY_2])
    assert exc.value.status_code == 409


def test_job_posts_in_given_order_and_cleans_up(output, monkeypatch):
    urls = []

    def fake(url, on_stage=None):
        urls.append(url)
        return {"media_id": f"M{len(urls)}", "permalink": None}

    monkeypatch.setattr(webapp, "publish_story", fake)
    webapp.POST_JOB.update(running=True, results=[], total=2)
    webapp._run_post_job([output / STORY_2, output / STORY_1], "https://example.test")
    assert webapp.POST_JOB["ok"] and webapp.POST_JOB["percent"] == 100
    assert [r["path"] for r in webapp.POST_JOB["results"]] == [STORY_2, STORY_1]
    assert all(u.startswith("https://example.test/p/") and u.endswith(".jpg") for u in urls)
    assert not webapp.PUBLIC_IMAGES


def test_job_failure_stops_series_and_reports_what_was_posted(output, monkeypatch):
    calls = []

    def fake(url, on_stage=None):
        calls.append(url)
        if len(calls) == 2:
            raise InstagramError("boom")
        return {"media_id": "M1", "permalink": None}

    monkeypatch.setattr(webapp, "publish_story", fake)
    webapp.POST_JOB.update(running=True, results=[], total=2)
    webapp._run_post_job([output / STORY_1, output / STORY_2], "https://example.test")
    assert webapp.POST_JOB["ok"] is False and webapp.POST_JOB["error"] == "boom"
    assert len(webapp.POST_JOB["results"]) == 1
    assert not webapp.PUBLIC_IMAGES and not webapp.POST_JOB["running"]
