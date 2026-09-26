from __future__ import annotations

import os
import secrets
import subprocess
import sys
from collections.abc import Iterator
from html import escape
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

# Thin web UI in front of the existing CLI: every button press just shells
# out to `python -m tvo_social.cli <command>` (same entry point as
# generate_posts.sh/generate_results.sh) so none of the image-generation
# logic is duplicated here.

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_ROOT = REPO_ROOT / "output"
WEB_STATIC_DIR = Path(__file__).resolve().parent / "web_static"
BASIC_AUTH_USERNAME = "TVOberwil"

# Marks the end of a streamed run for the browser to detect - "__DONE__" is
# not something normal CLI output would ever print by coincidence.
DONE_MARKER = "__DONE__"

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


def stream_cli(*command_lists: list[str]) -> Iterator[str]:
    """Run one or more CLI commands in sequence, yielding output line by
    line as it's produced (stderr interleaved with stdout in real time,
    rather than appended afterwards) so the browser can show live progress
    instead of a page that just hangs until the whole thing is done.
    Stops early if a command fails; a later command only runs if the
    previous one succeeded (mirrors `announce` then `story`)."""
    for args in command_lists:
        yield f"\n=== tvo-social {' '.join(args)} ===\n"
        process = subprocess.Popen(
            # "-u": unbuffered stdout/stderr - without it, a non-tty pipe
            # makes CPython block-buffer output, so lines would only show up
            # in bursts (or all at once at exit) instead of live.
            [sys.executable, "-u", "-m", "tvo_social.cli", *args],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            yield line
        process.wait()
        if process.returncode != 0:
            yield f"{DONE_MARKER}:{process.returncode}\n"
            return
    yield f"{DONE_MARKER}:0\n"


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
            f"<a class='thumb' href='/files/{escape(rel)}' target='_blank'>"
            f"<img src='/files/{escape(rel)}' loading='lazy'>"
            f"<span>{escape(rel)}</span></a>"
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
  pre {{ background: #1a1a1a; color: #d4d4d4; padding: 12px; border-radius: 8px;
         overflow-x: auto; white-space: pre-wrap; font-size: 0.8rem; max-height: 40vh; }}
  .ok {{ color: #1a7d1a; font-weight: 600; }}
  .fail {{ color: #c8102e; font-weight: 600; }}
  .muted {{ color: #777; }}
  .gallery {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
              gap: 10px; }}
  .thumb {{ display: block; text-decoration: none; color: #333; font-size: 0.7rem; }}
  .thumb img {{ width: 100%; border-radius: 6px; display: block; }}
  #status {{ margin: 20px 0; }}
  .spinner {{ display: inline-block; width: 18px; height: 18px; border: 3px solid #ddd;
              border-top-color: #c8102e; border-radius: 50%; animation: spin 0.8s linear infinite;
              vertical-align: middle; margin-right: 8px; }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  .status-line {{ display: flex; align-items: center; font-weight: 600; }}
</style>
</head>
<body>
<h1>TV Oberwil Social</h1>
<div class="buttons">
  <button onclick="runJob('weekend')">Kommendes Wochenende</button>
  <button onclick="runJob('results')">Resultate generieren</button>
</div>
<div id="status" hidden>
  <div class="status-line"><span id="spinner" class="spinner"></span><span id="status-text"></span></div>
  <pre id="log"></pre>
</div>
<div id="galleries">
{galleries_block}
</div>
<script>
const BUTTON_LABELS = {{
  weekend: "Kommendes Wochenende",
  results: "Resultate generieren",
}};

async function runJob(kind) {{
  const buttons = document.querySelectorAll('.buttons button');
  buttons.forEach(b => b.disabled = true);

  const status = document.getElementById('status');
  const spinner = document.getElementById('spinner');
  const statusText = document.getElementById('status-text');
  const log = document.getElementById('log');
  status.hidden = false;
  spinner.hidden = false;
  statusText.textContent = (BUTTON_LABELS[kind] || kind) + ' läuft...';
  log.textContent = '';

  try {{
    const response = await fetch('/run/' + kind, {{ method: 'POST' }});
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let done = false;
    let exitCode = null;

    while (!done) {{
      const chunk = await reader.read();
      done = chunk.done;
      if (chunk.value) {{
        buffer += decoder.decode(chunk.value, {{ stream: true }});
        const markerIndex = buffer.indexOf('__DONE__:');
        if (markerIndex !== -1) {{
          log.textContent += buffer.slice(0, markerIndex);
          const rest = buffer.slice(markerIndex).match(/__DONE__:(-?\\d+)/);
          if (rest) exitCode = parseInt(rest[1], 10);
          buffer = '';
        }} else {{
          log.textContent += buffer;
          buffer = '';
        }}
        log.scrollTop = log.scrollHeight;
      }}
    }}

    spinner.hidden = true;
    if (exitCode === 0) {{
      statusText.innerHTML = "<span class='ok'>Fertig</span>";
    }} else {{
      statusText.innerHTML = "<span class='fail'>Fehler" + (exitCode !== null ? ' (Code ' + exitCode + ')' : '') + "</span>";
    }}

    const galleriesResponse = await fetch('/partial/galleries');
    document.getElementById('galleries').innerHTML = await galleriesResponse.text();
  }} catch (err) {{
    spinner.hidden = true;
    statusText.innerHTML = "<span class='fail'>Fehler: " + err + "</span>";
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


@app.post("/run/weekend")
def run_weekend(_: None = Depends(require_auth)) -> StreamingResponse:
    return StreamingResponse(stream_cli(["weekend"]), media_type="text/plain")


@app.post("/run/results")
def run_results(_: None = Depends(require_auth)) -> StreamingResponse:
    return StreamingResponse(stream_cli(["results"]), media_type="text/plain")


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
