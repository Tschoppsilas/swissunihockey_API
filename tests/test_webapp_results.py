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
    assert "Aktuelle Woche (Standard)" in html and "Letzte Woche" in html
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


def test_page_has_a_gallery_for_home_results_and_the_client_category_rules():
    html = webapp.render_page().body.decode()
    assert "Heimspiel-Resultate (Feed)" in html and "gallery-home_results" in html
    assert "['announcements', 'home_results'].includes(categoryOf(p))" in html
    assert "['story', 'results'].includes(categoryOf(p))" in html  # story: still no home_results


def test_progress_separates_story_and_feed_images():
    ctx = {}

    def parse(line):
        return webapp._parse_progress("results", line, ctx)

    story = parse("2026-W02: 12 Spiele -> 2 Bild(er)")
    wrote_story = parse("  geschrieben: output/results/2026-W02/post_1of2.png")
    found = parse("10 Heimspiel(e) gefunden - erzeuge zusaetzlich den Feed-Post.")
    feed = parse("2026-W02: 10 Spiele -> 2 Bild(er)")
    wrote_feed = parse(r"  geschrieben: output\home_results\2026-W02\post_1of2.png")
    assert "Story" in story[1] and "Story" in wrote_story[1]
    assert "Feed-Post" in feed[1] and "Feed-Post" in wrote_feed[1]
    percents = [story[0], wrote_story[0], found[0], feed[0], wrote_feed[0]]
    assert percents == sorted(percents)
    assert parse("Keine Heimspiele in diesem Zeitraum - kein Feed-Post noetig.")[0] == 98


def test_summary_counts_story_and_feed_images_separately():
    log = (
        "Zeitraum: 05.01.2026 - 11.01.2026\n"
        "2026-W02: 12 Spiele -> 2 Bild(er)\n  Titel: RESULTATE - 10.-11.01.\n"
        "  geschrieben: output/results/2026-W02/post_1of2.png\n"
        "  geschrieben: output/results/2026-W02/post_2of2.png\n"
        "\n10 Heimspiel(e) gefunden - erzeuge zusaetzlich den Feed-Post.\n"
        "2026-W02: 10 Spiele -> 2 Bild(er)\n"
        "  geschrieben: output/home_results/2026-W02/post_1of2.png\n"
        "  geschrieben: output/home_results/2026-W02/post_2of2.png\n"
    )
    summary = webapp._build_summary("results", log, True)
    assert "Erzeugt: 2 Story-Bilder + 2 Feed-Post-Bilder." in summary


def test_summary_says_when_there_were_no_home_games():
    log = (
        "2026-W43: 13 Spiele -> 2 Bild(er)\n  Titel: RESULTATE - 25.10.\n"
        "  geschrieben: output/results/2026-W43/post_1of2.png\n"
        "  geschrieben: output/results/2026-W43/post_2of2.png\n"
        "\nKeine Heimspiele in diesem Zeitraum - kein Feed-Post noetig.\n"
    )
    summary = webapp._build_summary("results", log, True)
    assert "Erzeugt: 2 Story-Bilder." in summary and "Keine Heimspiele in diesem Zeitraum" in summary
    assert "Feed-Post-Bild" not in summary
