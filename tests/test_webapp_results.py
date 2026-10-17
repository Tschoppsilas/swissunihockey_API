import pytest
from fastapi import HTTPException

from tvo_social import webapp


@pytest.mark.parametrize(
    "mode,day,expected",
    [
        ("current", "", ["--weekend", "current"]),
        ("last", "", ["--weekend", "last"]),
        ("date", "2026-10-11", ["--date", "2026-10-11"]),
    ],
)
def test_results_args_valid(mode, day, expected):
    assert webapp._results_args(mode, day) == expected


@pytest.mark.parametrize(
    "mode,day",
    [("date", ""), ("date", "11.10.2026"), ("date", "2026-13-40"), ("date", "x; rm -rf /"), ("bogus", ""), ("", "")],
)
def test_results_args_invalid_never_reach_the_subprocess(mode, day):
    with pytest.raises(HTTPException) as exc:
        webapp._results_args(mode, day)
    assert exc.value.status_code == 400


def test_start_job_passes_selection_to_the_job(monkeypatch):
    started = {}

    class FakeThread:
        def __init__(self, target, args, daemon):
            started["args"] = args

        def start(self):
            pass

    monkeypatch.setattr(webapp.threading, "Thread", FakeThread)
    webapp.JOB["running"] = False
    webapp.start_job("results", mode="date", day="2026-10-11", _=None)
    assert started["args"] == ("results", ["--date", "2026-10-11"])
    webapp.JOB["running"] = False
    webapp.start_job("weekend", mode="date", day="garbage", _=None)  # ignored for weekend
    assert started["args"] == ("weekend", [])


def test_page_has_the_weekend_selector():
    html = webapp.render_page().body.decode()
    assert "Aktuelles Wochenende (Standard)" in html and "Letztes Wochenende" in html
    assert 'type="date"' in html


def test_summary_names_the_games_period_and_the_fallback_note():
    log = (
        "Zeitraum: 05.10.2026 - 11.10.2026\n"
        "Hinweis: Diese Woche wurde noch nichts gespielt - zeige die letzte Woche mit gespielten Spielen.\n"
        "2026-W41: 2 Spiele -> 1 Bild(er)\n  Titel: RESULTATE - 11.10.\n"
        "  geschrieben: output/results/2026-W41/post_1of1.png\n"
    )
    summary = webapp._build_summary("results", log, True)
    assert "RESULTATE - 11.10." in summary and "noch nichts gespielt" in summary
