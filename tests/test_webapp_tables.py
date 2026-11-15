import pytest
from fastapi import HTTPException
from PIL import Image

from tvo_social import webapp

TABLES_1 = "tables/2026/junioren-d-regional.png"
TABLES_2 = "tables/2026/herren-aktive-gf-4-liga.png"
ANNOUNCE = "announcements/2026-W47/post_1of1.png"
HOME_RES = "home_results/2026-W46/post_1of2.png"
STORY = "story/2026-W47/post_1of1.png"


@pytest.fixture
def output(tmp_path, monkeypatch):
    for rel in (TABLES_1, TABLES_2, ANNOUNCE, HOME_RES, STORY):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1080, 1350), "grey").save(path)
    monkeypatch.setattr(webapp, "OUTPUT_ROOT", tmp_path)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.test")

    class NoopThread:
        def __init__(self, target, args, daemon):
            pass

        def start(self):
            pass

    monkeypatch.setattr(webapp.threading, "Thread", NoopThread)
    webapp.POST_JOB.update(running=False, done=False, results=[], posted_paths=[], error="")
    webapp.JOB["running"] = False
    return tmp_path


# --- the button and its "Zusatz" choice ---


@pytest.mark.parametrize(
    "label,expected",
    [("", []), ("winterpause", ["--label", "Winterpause"]), ("saisonende", ["--label", "Saisonende"])],
)
def test_the_zusatz_choice_becomes_the_cli_label(label, expected):
    assert webapp._job_args("tables", "", "", "", label) == expected


@pytest.mark.parametrize("label", ["Winterpause", "WINTERPAUSE", "schlusstabelle", "x; rm -rf /", "--label"])
def test_an_unknown_zusatz_is_refused(label):
    with pytest.raises(HTTPException) as exc:
        webapp._job_args("tables", "", "", "", label)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("mode,day,scope", [("date", "", ""), ("", "2026-11-15", ""), ("", "", "day"), ("current", "", "")])
def test_period_values_are_refused_for_tables(mode, day, scope):
    with pytest.raises(HTTPException) as exc:
        webapp._job_args("tables", mode, day, scope, "")
    assert exc.value.status_code == 400


@pytest.mark.parametrize("kind", ["weekend", "results"])
def test_a_zusatz_is_refused_for_the_other_buttons(kind):
    with pytest.raises(HTTPException) as exc:
        webapp._job_args(kind, "", "", "", "winterpause")
    assert exc.value.status_code == 400


def test_the_other_buttons_still_use_the_period_selector():
    assert webapp._job_args("results", "last", "", "", "") == ["--weekend", "last"]
    assert webapp._job_args("weekend", "date", "2026-11-15", "week", "") == ["--date", "2026-11-15", "--scope", "week"]


def test_start_job_passes_the_label_to_the_tables_job(monkeypatch):
    started = {}

    class FakeThread:
        def __init__(self, target, args, daemon):
            started["args"] = args

        def start(self):
            pass

    monkeypatch.setattr(webapp.threading, "Thread", FakeThread)
    webapp.JOB["running"] = False
    webapp.start_job("tables", label="winterpause", _=None)
    assert started["args"] == ("tables", ["--label", "Winterpause"])
    webapp.JOB["running"] = False
    webapp.start_job("tables", _=None)
    assert started["args"] == ("tables", [])
    webapp.JOB["running"] = False
    with pytest.raises(HTTPException):
        webapp.start_job("tables", label="bogus", _=None)
    assert not webapp.JOB["running"]


def test_tables_is_a_registered_job_but_has_no_period_preview():
    assert webapp.JOB_COMMANDS["tables"] == [["tables"]]
    with pytest.raises(HTTPException) as exc:
        webapp.period_preview("tables", "2026-11-15", "day", None)
    assert exc.value.status_code == 404


def test_page_has_the_button_the_dropdown_and_the_gallery():
    html = webapp.render_page().body.decode()
    assert "Tabellen generieren" in html and 'runJob(\'tables\')' in html
    assert 'id="tables-label"' in html
    for text in ("Kein Zusatz (Standard)", "Winterpause", "Saisonende"):
        assert text in html
    assert 'value="winterpause"' in html and 'value="saisonende"' in html and 'option value=""' in html
    assert "Tabellen (Feed)" in html and "gallery-tables" in html
    assert "'/run/tables?label='" in html
    assert 'tables: "Tabellen generieren"' in html


# --- progress and summary ---


def test_progress_bar_follows_the_real_steps():
    ctx = {}

    def parse(line):
        return webapp._parse_progress("tables", line, ctx)

    steps = [
        parse("[progress] Tabelle 1/9 geladen"),
        parse("[progress] Tabelle 9/9 geladen"),
        parse("[progress] Bild 1/7 erstellt"),
        parse("[progress] Bild 7/7 erstellt"),
    ]
    percents = [p for p, _ in steps]
    assert percents == sorted(percents) and percents[0] >= 5 and percents[-1] == 98
    assert steps[1][1] == "Lade Tabellen (9/9)..." and steps[3][1] == "Erstelle Tabellen-Bild 7/7..."
    assert parse("Tabelle: Junioren D Regional - 10 Teams, TVO: TVO D Rot") is None
    assert parse("Keine Tabellen erzeugt.") == (100, "Keine Tabellen erzeugt.")


FULL_LOG = (
    "Titel-Zusatz: Winterpause\n"
    "[progress] Tabelle 1/9 geladen\n"
    "Junioren E: ausgeschlossen (Konfiguration)\n"
    "Hinweis: Ungleiche Spielzahl: U16, U18 (laufender Spieltag?)\n"
    "Tabelle: Herren Aktive GF 4. Liga - 10 Teams, TVO: TV Oberwil\n"
    "  geschrieben: output\\tables\\2026\\herren-aktive-gf-4-liga.png (Skalierung 1.08)\n"
    "[progress] Bild 1/2 erstellt\n"
    "  geschrieben: output\\tables\\2026\\junioren-d-regional.png (Skalierung 1.08)\n"
    "[progress] Bild 2/2 erstellt\n"
    "Entfernt (veraltet): alt.png\n"
    "\nZusammenfassung: 2 Bild(er), 1 Tabelle(n) uebersprungen\n"
    "UEBERSPRUNGEN: U18 (Junioren U18 C): keine Tabelle (404)\n"
)


def test_summary_names_images_addition_skips_exclusion_and_uneven_games():
    summary = webapp._build_summary("tables", FULL_LOG, True)
    assert "Erzeugt: 2 Tabellen-Bilder (Saison 2026). Zusatz: Winterpause." in summary
    assert "Übersprungen: U18 (Junioren U18 C): keine Tabelle (404)" in summary
    assert "Junioren E: ausgeschlossen (Konfiguration)" in summary
    assert "Ungleiche Spielzahl: U16, U18 (laufender Spieltag?)" in summary
    assert "geschrieben" not in summary and "[progress]" not in summary  # no raw console output


def test_summary_without_zusatz_and_with_one_image():
    log = (
        "Titel-Zusatz: keiner\n"
        "  geschrieben: output/tables/2025/junioren-c-regional.png (Skalierung 1.04)\n"
    )
    summary = webapp._build_summary("tables", log, True)
    assert summary.startswith("Erzeugt: 1 Tabellen-Bild (Saison 2025). Kein Zusatz.")
    assert "Zusatz: keiner" not in summary


def test_summary_when_nothing_was_produced_still_gives_the_reasons():
    log = (
        "Titel-Zusatz: Saisonende\n"
        "UEBERSPRUNGEN: U18 (Junioren U18 C): keine Tabelle (404)\n"
        "\nZusammenfassung: 0 Bild(er), 1 Tabelle(n) uebersprungen\nKeine Tabellen erzeugt.\n"
    )
    summary = webapp._build_summary("tables", log, True)
    assert summary.startswith("Keine Tabellen erzeugt. Zusatz: Saisonende.")
    assert "Übersprungen: U18 (Junioren U18 C): keine Tabelle (404)" in summary


def test_summary_of_a_failed_run_is_the_generic_error():
    assert "Fehler" in webapp._build_summary("tables", FULL_LOG, False)


def test_summary_escapes_html_from_the_log():
    summary = webapp._build_summary("tables", "Titel-Zusatz: <b>x</b>\nUEBERSPRUNGEN: <i>y</i>: z\n", True)
    assert "<b>" not in summary and "<i>" not in summary


# --- gallery and availability ---


def test_the_gallery_lists_the_table_images_of_every_season_once(output):
    old = output / "tables/2025/junioren-c-regional.png"
    old.parent.mkdir(parents=True)
    Image.new("RGB", (10, 10)).save(old)
    html = webapp.render_galleries_block()
    section = html.split("<h2>Tabellen (Feed)</h2>")[1]
    for rel in (TABLES_1, TABLES_2, "tables/2025/junioren-c-regional.png"):
        assert section.count(f"data-path='{rel}'") == 1, rel
    assert "Tabellen (Feed)" in html and section.index("tables/2026") < section.index("tables/2025")  # newest first


def test_table_images_stay_downloadable_while_the_app_runs(output):
    response = webapp.get_file(TABLES_1, None)
    assert response.path == output / TABLES_1 or str(response.path).endswith("junioren-d-regional.png")
    with pytest.raises(HTTPException):
        webapp.get_file("tables/2026/gibt-es-nicht.png", None)
    with pytest.raises(HTTPException):
        webapp.get_file("tables/../../etc/passwd", None)


# --- posting: Feed yes, Story no ---


def start_feed(paths, caption=""):
    return webapp.start_feed_post(webapp.FeedPostRequest(paths=paths, caption=caption), None)


def start_story(paths):
    return webapp.start_story_post(webapp.StoryPostRequest(paths=paths), None)


def test_a_single_table_image_can_be_posted_as_a_feed_post(output):
    assert start_feed([TABLES_1], "Tabelle") == {"started": True}


def test_a_carousel_may_mix_every_feed_type_in_the_chosen_order(output, monkeypatch):
    captured = {}

    class CapturingThread:
        def __init__(self, target, args, daemon):
            captured["files"] = args[0]

        def start(self):
            pass

    monkeypatch.setattr(webapp.threading, "Thread", CapturingThread)
    order = [TABLES_2, ANNOUNCE, TABLES_1, HOME_RES]
    assert start_feed(order, "Mix") == {"started": True}
    assert [p.relative_to(output).as_posix() for p in captured["files"]] == order


def test_a_carousel_is_limited_to_ten_images(output):
    with pytest.raises(HTTPException) as exc:
        start_feed([TABLES_1] * 3 + [f"tables/2026/x{i}.png" for i in range(8)])
    assert exc.value.status_code == 400


def test_table_images_are_refused_as_a_story(output):
    with pytest.raises(HTTPException) as exc:
        start_story([TABLES_1])
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException):
        start_story([STORY, TABLES_1])
    assert not webapp.POST_JOB["running"]


def test_story_images_are_still_refused_as_feed(output):
    with pytest.raises(HTTPException):
        start_feed([TABLES_1, STORY])


def test_the_client_rules_match_the_server():
    html = webapp.render_page().body.decode()
    assert "['announcements', 'home_results', 'tables'].includes(categoryOf(p))" in html  # feed
    assert "['story', 'results'].includes(categoryOf(p))" in html  # story: no tables
    assert "Feed-Bilder (Ankündigungen, Heimspiel-Resultate oder Tabellen)" in html
