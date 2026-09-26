from __future__ import annotations

import os
import secrets
import subprocess
import sys
from html import escape
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

# Thin web UI in front of the existing CLI: every button press just shells
# out to `python -m tvo_social.cli <command>` (same entry point as
# generate_posts.sh/generate_results.sh) so none of the image-generation
# logic is duplicated here.

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_ROOT = REPO_ROOT / "output"
BASIC_AUTH_USERNAME = "TVOberwil"

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


def run_cli(*args: str) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, "-m", "tvo_social.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    return result.returncode == 0, output


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


PAGE_TEMPLATE = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TV Oberwil Social</title>
<style>
  body {{ font-family: -apple-system, Helvetica, Arial, sans-serif; margin: 0; padding: 16px;
         background: #f5f5f5; color: #1a1a1a; }}
  h1 {{ font-size: 1.3rem; }}
  h2 {{ font-size: 1.05rem; margin-top: 2rem; }}
  .buttons {{ display: flex; flex-direction: column; gap: 12px; margin: 20px 0; }}
  button {{ font-size: 1.05rem; padding: 14px; border: none; border-radius: 10px;
            background: #c8102e; color: white; font-weight: 600; }}
  button:active {{ background: #a10d25; }}
  pre {{ background: #1a1a1a; color: #d4d4d4; padding: 12px; border-radius: 8px;
         overflow-x: auto; white-space: pre-wrap; font-size: 0.8rem; }}
  .ok {{ color: #1a7d1a; font-weight: 600; }}
  .fail {{ color: #c8102e; font-weight: 600; }}
  .muted {{ color: #777; }}
  .gallery {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
              gap: 10px; }}
  .thumb {{ display: block; text-decoration: none; color: #333; font-size: 0.7rem; }}
  .thumb img {{ width: 100%; border-radius: 6px; display: block; }}
</style>
</head>
<body>
<h1>TV Oberwil Social</h1>
<form method="post" action="/run/announce" class="buttons">
  <button type="submit">Ankündigungen generieren</button>
</form>
<form method="post" action="/run/results" class="buttons">
  <button type="submit">Resultate generieren</button>
</form>
{result_html}
<h2>Ankündigungen (Feed)</h2>
{announcements_gallery}
<h2>Story</h2>
{story_gallery}
<h2>Resultate</h2>
{results_gallery}
</body>
</html>
"""


def render_page(result_html: str = "") -> HTMLResponse:
    html = PAGE_TEMPLATE.format(
        result_html=result_html,
        announcements_gallery=render_gallery("announcements"),
        story_gallery=render_gallery("story"),
        results_gallery=render_gallery("results"),
    )
    return HTMLResponse(html)


@app.get("/", response_class=HTMLResponse)
def index(_: None = Depends(require_auth)) -> HTMLResponse:
    return render_page()


def _result_block(steps: list[tuple[str, bool, str]]) -> str:
    parts = ["<h2>Ergebnis</h2>"]
    for label, ok, output in steps:
        status = "<span class='ok'>OK</span>" if ok else "<span class='fail'>FEHLER</span>"
        parts.append(f"<p>{escape(label)}: {status}</p><pre>{escape(output)}</pre>")
    return "".join(parts)


@app.post("/run/announce", response_class=HTMLResponse)
def run_announce(_: None = Depends(require_auth)) -> HTMLResponse:
    steps = []
    ok, output = run_cli("announce")
    steps.append(("announce", ok, output))
    if ok:
        ok2, output2 = run_cli("story")
        steps.append(("story", ok2, output2))
    return render_page(_result_block(steps))


@app.post("/run/results", response_class=HTMLResponse)
def run_results(_: None = Depends(require_auth)) -> HTMLResponse:
    ok, output = run_cli("results")
    return render_page(_result_block([("results", ok, output)]))


@app.get("/files/{path:path}")
def get_file(path: str, _: None = Depends(require_auth)) -> FileResponse:
    target = (OUTPUT_ROOT / path).resolve()
    if OUTPUT_ROOT.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404, "Datei nicht gefunden.")
    return FileResponse(target)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
