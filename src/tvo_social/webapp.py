from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys
import threading
from html import escape
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .instagram import InstagramError, check_connection

# Thin web UI in front of the existing CLI: every button press just shells
# out to `python -m tvo_social.cli <command>` (same entry point as
# generate_posts.sh/generate_results.sh) so none of the image-generation
# logic is duplicated here.
#
# Progress is reported via polling (GET /run/status) rather than a streamed
# HTTP response: an earlier version streamed the subprocess output directly
# as the HTTP response body, which worked locally but arrived all at once
# (or not at all until the end) through Render's reverse proxy - Render
# apparently buffers long-lived streaming responses. Polling every ~1.2s
# uses only short, complete request/response cycles, so it can't be broken
# by that kind of upstream buffering.

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_ROOT = REPO_ROOT / "output"
WEB_STATIC_DIR = Path(__file__).resolve().parent / "web_static"
BASIC_AUTH_USERNAME = "TVOberwil"

JOB_COMMANDS: dict[str, list[list[str]]] = {
    "weekend": [["weekend"]],
    "results": [["results"]],
}

JOB_LOCK = threading.Lock()
JOB: dict = {
    "kind": None,
    "running": False,
    "percent": 0,
    "message": "",
    "log": "",
    "summary": "",
    "done": False,
    "ok": None,
}

TEAM_PROGRESS_RE = re.compile(r"\[progress\] Team (\d+)/(\d+) geladen \(status=(\w+)\)")
WEEK_SUMMARY_RE = re.compile(r"^\d{4}-W\d+: \d+ Spiele")
WROTE_STORY_RE = re.compile(r"geschrieben:.*[/\\]story[/\\]")
WROTE_FEED_RE = re.compile(r"geschrieben:.*[/\\]announcements[/\\]")
WROTE_RESULTS_RE = re.compile(r"geschrieben:.*[/\\]results[/\\]")

app = FastAPI(title="TV Oberwil Social")
security = HTTPBasic()


def require_auth(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    expected_password = os.environ.get("TVO_SOCIAL_PASSWORD")
    if not expected_password:
        raise HTTPException(500, "TVO_SOCIAL_PASSWORD ist nicht gesetzt.")
    valid_user = secrets.compare_digest(credentials.username, BASIC_AUTH_USERNAME)
    valid_pass = secrets.compare_digest(credentials.password, expected_password)
    if not (valid_user and valid_pass):
        raise HTTPException(
            401, "Falscher Benutzername oder Passwort.", headers={"WWW-Authenticate": "Basic"}
        )


def _parse_progress(kind: str, line: str, ctx: dict) -> tuple[int, str] | None:
    """Map one line of CLI output to a (percent, message) update, based on
    real, already-completed steps rather than a time-based guess - fetching
    each team's fixtures over HTTP is by far the slowest part of any
    command, so that loop (see cli._fetch_team_games's "[progress]" lines)
    carries most of the bar; rendering is comparatively instant."""
    match = TEAM_PROGRESS_RE.search(line)
    if match:
        done, total, status = int(match[1]), int(match[2]), match[3]
        fraction = done / total if total else 1.0
        if kind == "results":
            # Two fetch passes here: "played" (0-45%) then "planned" (45-85%).
            if status == "played":
                return 5 + round(fraction * 40), f"Lade gespielte Resultate ({done}/{total})..."
            return 45 + round(fraction * 40), f"Lade ausstehende Spiele ({done}/{total})..."
        return 5 + round(fraction * 70), f"Lade Spieldaten ({done}/{total})..."

    if WEEK_SUMMARY_RE.search(line):
        if kind == "results":
            return 88, "Erstelle Resultate-Bild(er)..."
        ctx["week_summaries"] = ctx.get("week_summaries", 0) + 1
        if ctx["week_summaries"] == 1:
            return 80, "Erstelle Story-Bild(er)..."
        return 90, "Erstelle Feed-Post-Bild(er)..."

    if "Heimspiel(e) gefunden" in line:
        return 90, "Heimspiel gefunden - erstelle Feed-Post..."
    if "Kein Heimspiel am kommenden Wochenende" in line:
        return 98, "Kein Heimspiel - fertig."
    if "Keine Spiele am kommenden Wochenende gefunden" in line:
        return 100, "Keine Spiele am kommenden Wochenende gefunden."
    if "Keine Resultate im Zeitraum gefunden" in line:
        return 100, "Keine Resultate im Zeitraum gefunden."

    if WROTE_STORY_RE.search(line):
        return 88, "Story-Bild gespeichert."
    if WROTE_FEED_RE.search(line):
        return 97, "Feed-Post-Bild gespeichert."
    if WROTE_RESULTS_RE.search(line):
        return 95, "Resultate-Bild gespeichert."

    return None


def _run_job(kind: str) -> None:
    with JOB_LOCK:
        JOB.update(
            kind=kind, running=True, percent=2, message="Starte...", log="", summary="", done=False, ok=None
        )

    ctx: dict = {}
    ok = True
    for args in JOB_COMMANDS[kind]:
        process = subprocess.Popen(
            # "-u": unbuffered stdout/stderr, so lines are available to read
            # as soon as the subprocess prints them instead of sitting in a
            # block buffer until it exits.
            [sys.executable, "-u", "-m", "tvo_social.cli", *args],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            update = _parse_progress(kind, line, ctx)
            with JOB_LOCK:
                JOB["log"] += line
                if update:
                    JOB["percent"], JOB["message"] = update
        process.wait()
        if process.returncode != 0:
            ok = False
            break

    with JOB_LOCK:
        JOB["running"] = False
        JOB["done"] = True
        JOB["ok"] = ok
        JOB["message"] = "Fertig." if ok else "Fehler."
        JOB["summary"] = _build_summary(kind, JOB["log"], ok)
        if ok:
            JOB["percent"] = 100


def _build_summary(kind: str, log_text: str, ok: bool) -> str:
    """Short, human-readable result instead of the raw CLI output - counts
    written images and any "FEHLENDE HALLE:"/"FEHLENDES RESULTAT:" warnings
    from the log, the same information generate_posts.sh's own end-of-run
    summary prints, just derived from this run's log instead of grepped
    from a temp file."""
    if not ok:
        return "<span class='fail'>Fehler bei der Generierung - Details siehe Render-Logs.</span>"

    lines = log_text.splitlines()
    story_count = sum(1 for l in lines if WROTE_STORY_RE.search(l))
    feed_count = sum(1 for l in lines if WROTE_FEED_RE.search(l))
    results_count = sum(1 for l in lines if WROTE_RESULTS_RE.search(l))
    missing_venues = sum(1 for l in lines if "FEHLENDE HALLE:" in l)
    missing_results = sum(1 for l in lines if "FEHLENDES RESULTAT:" in l)

    def plural(n: int, noun: str) -> str:
        return f"{n} {noun}" if n == 1 else f"{n} {noun}er"

    if kind == "weekend":
        if story_count == 0 and feed_count == 0:
            return "Keine Spiele am kommenden Wochenende gefunden."
        parts = [plural(story_count, "Story-Bild")]
        if feed_count:
            parts.append(plural(feed_count, "Feed-Post-Bild"))
        summary = "Erzeugt: " + " + ".join(parts) + "."
    else:
        if results_count == 0:
            return "Keine Resultate im Zeitraum gefunden."
        summary = f"Erzeugt: {plural(results_count, 'Resultate-Bild')}."

    if missing_venues:
        summary += f"<div class='warn'>⚠ {missing_venues} Spiel(e) ohne Hallen-Zuweisung</div>"
    if missing_results:
        summary += f"<div class='warn'>⚠ {missing_results} Spiel(e) ohne Resultat</div>"
    return summary


def list_generated_images(category: str) -> list[Path]:
    category_dir = OUTPUT_ROOT / category
    if not category_dir.exists():
        return []
    return sorted(category_dir.glob("*/*.png"), reverse=True)


def render_gallery(category: str) -> str:
    images = list_generated_images(category)
    if not images:
        return "<p class='muted'>Noch keine Bilder vorhanden.</p>"
    items = []
    for path in images:
        rel = path.relative_to(OUTPUT_ROOT).as_posix()
        items.append(
            f"<div class='thumb' data-path='{escape(rel)}' onclick='toggleSelect(this)'>"
            f"<img src='/files/{escape(rel)}' loading='lazy'>"
            f"<span class='badge' hidden></span>"
            f"<a class='view-link' href='/files/{escape(rel)}' target='_blank' "
            f"onclick='event.stopPropagation()'>&#10021;</a>"
            f"<span class='caption'>{escape(rel)}</span></div>"
        )
    return f"<div class='gallery'>{''.join(items)}</div>"


def render_galleries_block() -> str:
    return (
        "<h2>Ankündigungen (Feed)</h2>"
        f"<div id='gallery-announcements'>{render_gallery('announcements')}</div>"
        "<h2>Story</h2>"
        f"<div id='gallery-story'>{render_gallery('story')}</div>"
        "<h2>Resultate</h2>"
        f"<div id='gallery-results'>{render_gallery('results')}</div>"
    )


PAGE_TEMPLATE = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TV Oberwil Social</title>
<link rel="manifest" href="/manifest.json">
<link rel="icon" type="image/x-icon" href="/favicon.ico">
<link rel="icon" type="image/png" sizes="192x192" href="/icons/icon-192.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta name="theme-color" content="#c8102e">
<style>
  body {{ font-family: -apple-system, Helvetica, Arial, sans-serif; margin: 0; padding: 16px;
         background: #f5f5f5; color: #1a1a1a; }}
  h1 {{ font-size: 1.3rem; }}
  h2 {{ font-size: 1.05rem; margin-top: 2rem; }}
  .buttons {{ display: flex; flex-direction: column; gap: 12px; margin: 20px 0; }}
  button {{ font-size: 1.05rem; padding: 14px; border: none; border-radius: 10px;
            background: #c8102e; color: white; font-weight: 600; }}
  button:active {{ background: #a10d25; }}
  button:disabled {{ background: #d99; }}
  .ok {{ color: #1a7d1a; font-weight: 600; }}
  .fail {{ color: #c8102e; font-weight: 600; }}
  .warn {{ color: #b45309; font-weight: 600; margin-top: 4px; }}
  .muted {{ color: #777; }}
  .gallery {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
              gap: 10px; }}
  .thumb {{ position: relative; text-decoration: none; color: #333; font-size: 0.7rem;
            cursor: pointer; border: 3px solid transparent; border-radius: 9px; padding: 2px; }}
  .thumb.selected {{ border-color: #c8102e; }}
  .thumb img {{ width: 100%; border-radius: 6px; display: block; }}
  .thumb .caption {{ display: block; }}
  .thumb .badge {{ position: absolute; top: 6px; left: 6px; width: 24px; height: 24px;
                    background: #c8102e; color: #fff; border-radius: 50%; display: flex;
                    align-items: center; justify-content: center; font-weight: 700; font-size: 0.85rem; }}
  .thumb .badge[hidden] {{ display: none; }}
  .thumb .view-link {{ position: absolute; top: 6px; right: 6px; width: 22px; height: 22px;
                        background: rgba(0,0,0,0.55); color: #fff; border-radius: 50%; display: flex;
                        align-items: center; justify-content: center; text-decoration: none; font-size: 0.8rem; }}
  .selection-bar {{ margin: 20px 0; background: #fff; border-radius: 10px; padding: 12px; }}
  .selection-bar[hidden] {{ display: none; }}
  .selection-bar h2 {{ margin-top: 0; }}
  .selection-list {{ display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }}
  .sel-item {{ display: flex; align-items: center; gap: 10px; }}
  .sel-item .sel-num {{ background: #c8102e; color: #fff; width: 22px; height: 22px; border-radius: 50%;
                         display: flex; align-items: center; justify-content: center; font-weight: 700;
                         font-size: 0.8rem; flex-shrink: 0; }}
  .sel-item img {{ width: 48px; height: 48px; object-fit: cover; border-radius: 6px; flex-shrink: 0; }}
  .sel-item .sel-path {{ flex: 1; font-size: 0.75rem; color: #555; overflow-wrap: anywhere; }}
  .sel-item .sel-controls {{ display: flex; gap: 4px; flex-shrink: 0; }}
  .sel-item .sel-controls button {{ padding: 6px 10px; font-size: 0.85rem; border-radius: 6px; }}
  .caption-field {{ width: 100%; box-sizing: border-box; padding: 10px; border-radius: 8px;
                     border: 1px solid #ccc; font-family: inherit; font-size: 0.9rem; margin-bottom: 10px;
                     resize: vertical; }}
  .selection-buttons {{ display: flex; flex-direction: column; gap: 10px; }}
  .post-preview {{ margin-top: 10px; font-size: 0.85rem; color: #444; white-space: pre-line; }}
  #status {{ margin: 20px 0; }}
  .status-line {{ display: flex; align-items: center; gap: 8px; font-weight: 600; margin-bottom: 6px; }}
  .spinner {{ display: inline-block; width: 16px; height: 16px; border: 3px solid #ddd;
              border-top-color: #c8102e; border-radius: 50%; animation: spin 0.8s linear infinite;
              flex-shrink: 0; }}
  .checkmark {{ display: inline-block; width: 16px; color: #1a7d1a; font-weight: 900;
                font-size: 1.1rem; line-height: 1; flex-shrink: 0; }}
  /* Without this, [hidden] loses to the two rules above: both set
     `display` at the same specificity as the browser's own built-in
     hidden-attribute rule, and author styles always beat the user-agent
     stylesheet at an equal-specificity tie - so toggling the `hidden`
     property from JS silently did nothing for these two. */
  .spinner[hidden], .checkmark[hidden] {{ display: none !important; }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  .progress-track {{ background: #ddd; border-radius: 8px; height: 18px; overflow: hidden; }}
  .progress-fill {{ background: #c8102e; height: 100%; width: 0%; transition: width 0.4s ease; }}
  .progress-percent {{ font-size: 0.8rem; color: #555; margin: 4px 0 10px; }}
  .summary {{ font-size: 0.95rem; }}
</style>
</head>
<body>
<h1>TV Oberwil Social</h1>
<div class="buttons">
  <button onclick="runJob('weekend')">Kommendes Wochenende</button>
  <button onclick="runJob('results')">Resultate generieren</button>
</div>
<div class="buttons">
  <button id="ig-check-btn" onclick="checkInstagram()">Instagram-Verbindung testen</button>
  <div id="ig-check-result"></div>
</div>
<div id="status" hidden>
  <div class="status-line">
    <span id="spinner" class="spinner"></span><span id="checkmark" class="checkmark" hidden>&#10003;</span>
    <span id="status-text"></span>
  </div>
  <div class="progress-track"><div id="progress-fill" class="progress-fill"></div></div>
  <div id="progress-percent" class="progress-percent">0%</div>
  <div id="summary" class="summary"></div>
</div>
<div id="galleries">
{galleries_block}
</div>
<div id="selection-bar" class="selection-bar" hidden>
  <h2>Auswahl (<span id="selection-count">0</span>)</h2>
  <div id="selection-list" class="selection-list"></div>
  <textarea id="caption" class="caption-field" rows="3"
            placeholder="Bildunterschrift für den Feed-Post..."></textarea>
  <div class="selection-buttons">
    <button id="story-btn" onclick="confirmAndPost('story')" disabled>Als Story posten</button>
    <button id="feed-btn" onclick="confirmAndPost('feed')" disabled>Als Feed-Post posten</button>
  </div>
  <div id="post-preview" class="post-preview"></div>
</div>
<script>
const BUTTON_LABELS = {{
  weekend: "Kommendes Wochenende",
  results: "Resultate generieren",
}};

function renderStatus(s) {{
  document.getElementById('progress-fill').style.width = s.percent + '%';
  document.getElementById('progress-percent').textContent = s.percent + '%';
  const spinner = document.getElementById('spinner');
  const checkmark = document.getElementById('checkmark');
  const statusText = document.getElementById('status-text');
  const summary = document.getElementById('summary');
  if (s.done) {{
    spinner.hidden = true;
    checkmark.hidden = !s.ok;
    statusText.innerHTML = s.ok ? "<span class='ok'>Fertig</span>" : "<span class='fail'>Fehler</span>";
    summary.innerHTML = s.summary || '';
  }} else {{
    spinner.hidden = false;
    checkmark.hidden = true;
    statusText.textContent = s.message || 'Läuft...';
    summary.innerHTML = '';
  }}
}}

async function pollStatus() {{
  return new Promise((resolve, reject) => {{
    const timer = setInterval(async () => {{
      try {{
        const r = await fetch('/run/status');
        const s = await r.json();
        renderStatus(s);
        if (s.done) {{
          clearInterval(timer);
          resolve(s);
        }}
      }} catch (err) {{
        clearInterval(timer);
        reject(err);
      }}
    }}, 1200);
  }});
}}

// Cross-gallery selection state: an ordered list of image paths (e.g.
// "story/2026-W39/post_1of1.png"), survives a gallery refresh after
// generating new images (same path strings), reset only on full page load.
let selection = [];

function categoryOf(path) {{
  return path.split('/')[0];
}}

function toggleSelect(el) {{
  const path = el.dataset.path;
  const idx = selection.indexOf(path);
  if (idx === -1) {{
    selection.push(path);
  }} else {{
    selection.splice(idx, 1);
  }}
  renderSelection();
}}

function moveSelection(index, direction) {{
  const target = index + direction;
  if (target < 0 || target >= selection.length) return;
  [selection[index], selection[target]] = [selection[target], selection[index]];
  renderSelection();
}}

function removeSelection(index) {{
  selection.splice(index, 1);
  renderSelection();
}}

function renderSelection() {{
  document.querySelectorAll('.thumb').forEach(el => {{
    const idx = selection.indexOf(el.dataset.path);
    const badge = el.querySelector('.badge');
    if (idx === -1) {{
      el.classList.remove('selected');
      badge.hidden = true;
    }} else {{
      el.classList.add('selected');
      badge.hidden = false;
      badge.textContent = idx + 1;
    }}
  }});

  const bar = document.getElementById('selection-bar');
  bar.hidden = selection.length === 0;
  document.getElementById('selection-count').textContent = selection.length;
  document.getElementById('story-btn').disabled = selection.length === 0;
  document.getElementById('feed-btn').disabled = selection.length === 0;
  document.getElementById('post-preview').textContent = '';

  document.getElementById('selection-list').innerHTML = selection.map((path, i) => `
    <div class="sel-item">
      <span class="sel-num">${{i + 1}}</span>
      <img src="/files/${{path}}">
      <span class="sel-path">${{path}}</span>
      <span class="sel-controls">
        <button onclick="moveSelection(${{i}}, -1)" ${{i === 0 ? 'disabled' : ''}}>&uarr;</button>
        <button onclick="moveSelection(${{i}}, 1)" ${{i === selection.length - 1 ? 'disabled' : ''}}>&darr;</button>
        <button onclick="removeSelection(${{i}})">&times;</button>
      </span>
    </div>
  `).join('');
}}

function confirmAndPost(kind) {{
  if (selection.length === 0) return;

  const wrongCategory = kind === 'story'
    ? selection.find(p => !['story', 'results'].includes(categoryOf(p)))
    : selection.find(p => categoryOf(p) !== 'announcements');
  if (wrongCategory) {{
    alert(kind === 'story'
      ? 'Für "Als Story posten" bitte nur Story- oder Resultate-Bilder auswählen (nicht: ' + wrongCategory + ').'
      : 'Für "Als Feed-Post posten" bitte nur Ankündigungs-Bilder (Heimspiele) auswählen (nicht: ' + wrongCategory + ').');
    return;
  }}
  if (kind === 'feed' && selection.length > 10) {{
    alert('Ein Feed-Karussell erlaubt maximal 10 Bilder - bitte Auswahl reduzieren.');
    return;
  }}

  const label = kind === 'story' ? 'als Story' : 'als Feed-Post';
  if (!confirm(selection.length + ' Bild(er) ' + label + ' posten?')) return;

  // Posting itself isn't wired up yet (comes in the next step) - this
  // proves the selection/order data is captured correctly end to end.
  const order = selection.map((p, i) => (i + 1) + '. ' + p).join('\\n');
  document.getElementById('post-preview').textContent =
    'Bereit zum Posten (' + label + '), Posten-Funktion folgt als Nächstes:\\n' + order;
}}

async function checkInstagram() {{
  const btn = document.getElementById('ig-check-btn');
  const out = document.getElementById('ig-check-result');
  btn.disabled = true;
  out.textContent = 'Teste Verbindung...';
  try {{
    const r = await fetch('/instagram/check', {{ method: 'POST' }});
    const d = await r.json();
    out.textContent = d.message;
    out.className = d.ok ? 'ok' : 'fail';
  }} catch (err) {{
    out.textContent = 'Fehler: ' + err;
    out.className = 'fail';
  }} finally {{
    btn.disabled = false;
  }}
}}

async function runJob(kind) {{
  const buttons = document.querySelectorAll('.buttons button');
  buttons.forEach(b => b.disabled = true);

  const status = document.getElementById('status');
  status.hidden = false;
  document.getElementById('spinner').hidden = false;
  document.getElementById('checkmark').hidden = true;
  document.getElementById('status-text').textContent = (BUTTON_LABELS[kind] || kind) + ' wird gestartet...';
  document.getElementById('summary').innerHTML = '';
  document.getElementById('progress-fill').style.width = '0%';
  document.getElementById('progress-percent').textContent = '0%';

  try {{
    const startResponse = await fetch('/run/' + kind, {{ method: 'POST' }});
    if (!startResponse.ok) {{
      throw new Error(await startResponse.text());
    }}
    await pollStatus();

    const galleriesResponse = await fetch('/partial/galleries');
    document.getElementById('galleries').innerHTML = await galleriesResponse.text();
    renderSelection();
  }} catch (err) {{
    document.getElementById('spinner').hidden = true;
    document.getElementById('status-text').innerHTML = "<span class='fail'>Fehler: " + err + "</span>";
  }} finally {{
    buttons.forEach(b => b.disabled = false);
  }}
}}
</script>
</body>
</html>
"""


def render_page() -> HTMLResponse:
    return HTMLResponse(PAGE_TEMPLATE.format(galleries_block=render_galleries_block()))


@app.get("/", response_class=HTMLResponse)
def index(_: None = Depends(require_auth)) -> HTMLResponse:
    return render_page()


@app.get("/partial/galleries", response_class=HTMLResponse)
def partial_galleries(_: None = Depends(require_auth)) -> HTMLResponse:
    return HTMLResponse(render_galleries_block())


@app.post("/run/{kind}")
def start_job(kind: str, _: None = Depends(require_auth)) -> dict:
    if kind not in JOB_COMMANDS:
        raise HTTPException(404, "Unbekannte Aktion.")
    with JOB_LOCK:
        if JOB["running"]:
            raise HTTPException(409, "Es läuft bereits eine Generierung.")
    threading.Thread(target=_run_job, args=(kind,), daemon=True).start()
    return {"started": True}


@app.get("/run/status")
def get_status(_: None = Depends(require_auth)) -> dict:
    with JOB_LOCK:
        # "log" (raw CLI output) is kept server-side only, to build the
        # summary from - not sent to the browser, which shows the summary.
        return {key: value for key, value in JOB.items() if key != "log"}


@app.post("/instagram/check")
def instagram_check_endpoint(_: None = Depends(require_auth)) -> dict:
    try:
        info = check_connection()
    except InstagramError as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": f"Verbindung OK: @{info['username']}"}


@app.get("/files/{path:path}")
def get_file(path: str, _: None = Depends(require_auth)) -> FileResponse:
    target = (OUTPUT_ROOT / path).resolve()
    if OUTPUT_ROOT.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404, "Datei nicht gefunden.")
    return FileResponse(target)


# App-icon/manifest assets - deliberately public (no require_auth): they're
# just the club logo, and keeping them unauthenticated avoids any chance of
# Android/Chrome's "Add to Home Screen" icon-fetching step failing to send
# cached Basic Auth credentials.
@app.get("/manifest.json")
def get_manifest() -> FileResponse:
    return FileResponse(WEB_STATIC_DIR / "manifest.json", media_type="application/manifest+json")


@app.get("/favicon.ico")
def get_favicon() -> FileResponse:
    return FileResponse(WEB_STATIC_DIR / "favicon.ico")


@app.get("/apple-touch-icon.png")
def get_apple_touch_icon() -> FileResponse:
    return FileResponse(WEB_STATIC_DIR / "apple-touch-icon.png")


@app.get("/icons/{filename}")
def get_icon(filename: str) -> FileResponse:
    target = (WEB_STATIC_DIR / filename).resolve()
    if WEB_STATIC_DIR.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404, "Datei nicht gefunden.")
    return FileResponse(target)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
