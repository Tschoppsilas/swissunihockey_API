import pytest
from fastapi import HTTPException

from tvo_social import webapp


@pytest.mark.parametrize(
    "kind,mode,day,scope,expected",
    [
        ("results", "current", "", "", ["--weekend", "current"]),
        ("results", "last", "", "", ["--weekend", "last"]),
        ("results", "", "", "", ["--weekend", "current"]),  # no mode given: the default
        ("results", "date", "2026-10-11", "", ["--date", "2026-10-11", "--scope", "day"]),  # default: only that day
        ("results", "date", "2026-10-11", "weekend", ["--date", "2026-10-11", "--scope", "weekend"]),
        ("results", "date", "2026-10-11", "week", ["--date", "2026-10-11", "--scope", "week"]),
        ("weekend", "upcoming", "", "", ["--weekend", "upcoming"]),
        ("weekend", "after-next", "", "", ["--weekend", "after-next"]),
        ("weekend", "", "", "", ["--weekend", "upcoming"]),
        ("weekend", "date", "2026-11-15", "day", ["--date", "2026-11-15", "--scope", "day"]),  # a Sunday
        ("weekend", "date", "2026-11-14", "week", ["--date", "2026-11-14", "--scope", "week"]),  # a Saturday
    ],
)
def test_selection_args_valid(kind, mode, day, scope, expected):
    assert webapp._selection_args(kind, mode, day, scope) == expected


@pytest.mark.parametrize("kind", ["results", "weekend"])
@pytest.mark.parametrize("scope", ["month", "Day", "day; ls", "weekend,week"])
def test_unknown_scope_never_reaches_the_subprocess(kind, scope):
    with pytest.raises(HTTPException) as exc:
        webapp._selection_args(kind, "date", "2026-11-15", scope)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("kind,mode", [("results", "current"), ("weekend", "upcoming"), ("weekend", "")])
def test_a_scope_without_a_date_selection_is_refused_not_ignored(kind, mode):
    with pytest.raises(HTTPException) as exc:
        webapp._selection_args(kind, mode, "", "week")
    assert exc.value.status_code == 400


@pytest.mark.parametrize("kind", ["results", "weekend"])
@pytest.mark.parametrize(
    "mode,day",
    [("date", ""), ("date", "11.10.2026"), ("date", "2026-13-40"), ("date", "x; rm -rf /"), ("bogus", "")],
)
def test_selection_args_invalid_never_reach_the_subprocess(kind, mode, day):
    with pytest.raises(HTTPException) as exc:
        webapp._selection_args(kind, mode, day)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("kind,wrong_mode", [("results", "upcoming"), ("weekend", "current"), ("weekend", "last")])
def test_each_kind_only_accepts_its_own_modes(kind, wrong_mode):
    with pytest.raises(HTTPException):
        webapp._selection_args(kind, wrong_mode, "")


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
    assert started["args"] == ("results", ["--date", "2026-10-11", "--scope", "day"])
    webapp.JOB["running"] = False
    webapp.start_job("weekend", mode="date", day="2026-11-15", scope="weekend", _=None)
    assert started["args"] == ("weekend", ["--date", "2026-11-15", "--scope", "weekend"])
    webapp.JOB["running"] = False
    webapp.start_job("weekend", _=None)
    assert started["args"] == ("weekend", ["--weekend", "upcoming"])
    webapp.JOB["running"] = False
    with pytest.raises(HTTPException):
        webapp.start_job("weekend", mode="date", day="garbage", _=None)
    assert not webapp.JOB["running"]


def test_page_has_both_selectors_with_their_own_options():
    html = webapp.render_page().body.decode()
    for text in (
        "Kommendes Wochenende (Standard)", "Übernächstes Wochenende",
        "Aktuelle Woche (Standard)", "Letzte Woche",
    ):
        assert text in html
    assert html.count('type="date"') == 2
    for kind in ("weekend", "results"):
        assert f'id="{kind}-scope"' in html and f'id="{kind}-daterow"' in html
    for text in ("Nur dieser Tag", "Dieses Wochenende (Sa + So)", "Ganze Woche (Mo-So)"):
        assert html.count(text) == 2, text  # once per selector
    assert html.count('<option value="day">') == 2 and html.count('<option value="weekend">') == 2
    assert html.count('<option value="week">') == 2
    assert ".date-row[hidden]" in html  # a flex row would otherwise stay visible despite [hidden]
    assert 'id="weekend-mode"' in html and 'id="weekend-day"' in html
    assert 'id="results-mode"' in html and 'id="results-day"' in html
    assert 'value="after-next"' in html and 'value="upcoming"' in html


def test_summary_shows_the_period_the_server_used_for_weekend_and_results():
    weekend_log = (
        "Zeitraum: 16.11.2026 - 22.11.2026\n"
        "2026-W47: 9 Spiele -> 1 Bild(er)\n  Titel: GAME WEEKEND - 21.-22.11.\n"
        "  geschrieben: output/story/2026-W47/post_1of1.png\n"
        "\n3 Heimspiel(e) gefunden - erzeuge zusaetzlich den Feed-Post.\n"
        "2026-W47: 3 Spiele -> 1 Bild(er)\n  Titel: GAME WEEKEND - 21.-22.11.\n"
        "  geschrieben: output/announcements/2026-W47/post_1of1.png\n"
    )
    summary = webapp._build_summary("weekend", weekend_log, True)
    assert "Erzeugt: 1 Story-Bild + 1 Feed-Post-Bild." in summary
    assert "Zeitraum: 16.11.2026 - 22.11.2026" in summary
    assert summary.count("GAME WEEKEND - 21.-22.11.") == 1

    results_log = (
        "Zeitraum: 09.11.2026 - 15.11.2026\n"
        "2026-W46: 19 Spiele -> 3 Bild(er)\n  Titel: RESULTATE - 14.-15.11.\n"
        "  geschrieben: output/results/2026-W46/post_1of3.png\n"
    )
    assert "Zeitraum: 09.11.2026 - 15.11.2026" in webapp._build_summary("results", results_log, True)


def test_summary_when_the_period_has_no_games():
    assert webapp._build_summary("weekend", "Zeitraum: 23.11.2026 - 29.11.2026\nKeine Spiele im Zeitraum gefunden.\n", True) == (
        "Keine Spiele im Zeitraum gefunden. Zeitraum: 23.11.2026 - 29.11.2026."
    )


def test_summary_names_the_chosen_day_scope_when_there_are_no_games():
    day_log = "Zeitraum: 15.11.2026\nKeine Spiele am So 15.11.2026.\n"
    assert webapp._build_summary("weekend", day_log, True) == "Keine Spiele am So 15.11.2026."
    results_log = "Zeitraum: 15.11.2026\nKeine Spiele mit Resultat am So 15.11.2026.\n"
    assert webapp._build_summary("results", results_log, True) == "Keine Spiele mit Resultat am So 15.11.2026."
    weekend_log = "Zeitraum: 28.11.2026 - 29.11.2026\nKeine Spiele am Wochenende Sa 28.11. - So 29.11.\n"
    assert webapp._build_summary("weekend", weekend_log, True) == "Keine Spiele am Wochenende Sa 28.11. - So 29.11."


def test_progress_reports_the_no_games_line_as_it_is():
    ctx = {}
    percent, text = webapp._parse_progress("results", "Keine Spiele mit Resultat am So 15.11.2026.", ctx)
    assert percent == 100 and text == "Keine Spiele mit Resultat am So 15.11.2026."
    percent, text = webapp._parse_progress("weekend", "Keine Spiele in der Woche Mo 09.11. - So 15.11.", ctx)
    assert percent == 100 and "in der Woche" in text


def test_progress_messages_do_not_claim_it_is_the_coming_weekend():
    ctx = {}
    assert webapp._parse_progress("weekend", "Keine Spiele im Zeitraum gefunden.", ctx)[0] == 100
    assert webapp._parse_progress("weekend", "Kein Heimspiel im Zeitraum - kein Feed-Post noetig.", ctx)[0] == 98


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


# --- a date must never be silently ignored, and the preview comes from the server ---


@pytest.mark.parametrize("kind,mode", [("results", "current"), ("results", "last"), ("weekend", "upcoming"), ("weekend", "")])
def test_a_date_with_a_non_date_selection_is_refused_not_ignored(kind, mode):
    with pytest.raises(HTTPException) as exc:
        webapp._selection_args(kind, mode, "2026-11-15")
    assert exc.value.status_code == 400
    assert "Datum" in exc.value.detail


def test_start_job_refuses_a_date_with_the_default_selection(monkeypatch):
    monkeypatch.setattr(webapp.threading, "Thread", lambda target, args, daemon: pytest.fail("must not start"))
    webapp.JOB["running"] = False
    with pytest.raises(HTTPException) as exc:
        webapp.start_job("results", mode="current", day="2026-11-15", _=None)
    assert exc.value.status_code == 400
    assert not webapp.JOB["running"]


@pytest.mark.parametrize("kind", ["results", "weekend"])
@pytest.mark.parametrize(
    "day,picked,weekend_of_week",
    [
        ("2026-11-09", "Mo 09.11.2026", "Sa 14.11. - So 15.11."),
        ("2026-11-10", "Di 10.11.2026", "Sa 14.11. - So 15.11."),
        ("2026-11-11", "Mi 11.11.2026", "Sa 14.11. - So 15.11."),
        ("2026-11-12", "Do 12.11.2026", "Sa 14.11. - So 15.11."),
        ("2026-11-13", "Fr 13.11.2026", "Sa 14.11. - So 15.11."),
        ("2026-11-14", "Sa 14.11.2026", "Sa 14.11. - So 15.11."),
        ("2026-11-15", "So 15.11.2026", "Sa 14.11. - So 15.11."),
    ],
)
def test_period_preview_for_every_weekday_and_scope(kind, day, picked, weekend_of_week):
    assert webapp.period_preview(kind, day, "day", None) == {"text": f"Gewählt: {picked} -> nur dieser Tag"}
    assert webapp.period_preview(kind, day, "weekend", None)["text"] == f"Gewählt: {picked} -> {weekend_of_week}"
    assert webapp.period_preview(kind, day, "week", None)["text"] == f"Gewählt: {picked} -> Mo 09.11. - So 15.11."


def test_period_preview_defaults_to_the_day_and_handles_the_year_boundary():
    assert webapp.period_preview("results", "2026-11-15", "day", None)["text"] == (
        "Gewählt: So 15.11.2026 -> nur dieser Tag"
    )
    assert webapp.period_preview("results", "2027-01-01", "week", None)["text"] == (
        "Gewählt: Fr 01.01.2027 -> Mo 28.12.2026 - So 03.01.2027"
    )
    assert webapp.period_preview("weekend", "2026-12-31", "weekend", None)["text"] == (
        "Gewählt: Do 31.12.2026 -> Sa 02.01.2027 - So 03.01.2027"
    )


def test_period_preview_rejects_an_unknown_scope():
    with pytest.raises(HTTPException) as exc:
        webapp.period_preview("results", "2026-11-15", "month", None)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("day", ["", "15.11.2026", "2026-13-40", "morgen", "2026-11-15; ls"])
def test_period_preview_rejects_unreadable_dates(day):
    with pytest.raises(HTTPException) as exc:
        webapp.period_preview("results", day, "day", None)
    assert exc.value.status_code == 400


def test_period_preview_rejects_unknown_kind():
    with pytest.raises(HTTPException) as exc:
        webapp.period_preview("posten", "2026-11-15", "day", None)
    assert exc.value.status_code == 404


def test_page_wires_up_the_preview_and_the_consistency_checks():
    html = webapp.render_page().body.decode()
    for kind in ("weekend", "results"):
        assert f'id="{kind}-preview"' in html
        assert f"onDayChange('{kind}')" in html and f"onModeChange('{kind}')" in html
    for snippet in (
        "function readDay(kind)", "function syncMode(kind)", "async function updatePreview(kind)",
        "addEventListener('pageshow'", "Bitte ein Datum wählen.", "Das Datum ist nicht lesbar",
        "'/period?kind='", "'&scope='", "-daterow",
    ):
        assert snippet in html, snippet
