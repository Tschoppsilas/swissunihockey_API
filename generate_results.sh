#!/usr/bin/env bash
# Generates the TV Oberwil results story post for the last completed
# Mon-Sun weekend.
#
# Run this weekly (e.g. Sunday evening after the last game) - or anytime you
# want to (re)generate the most recent completed week's results. `announce`
# and `story` (upcoming games) are NOT run here - see generate_posts.sh for
# those.
#
# Usage: ./generate_results.sh   (run from anywhere - it cd's to its own folder)

set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -f "pyproject.toml" ]; then
    echo "FEHLER: pyproject.toml nicht gefunden - falsches Verzeichnis?" >&2
    exit 1
fi

TVO_SOCIAL="./.venv/Scripts/tvo-social.exe"
if [ ! -f "$TVO_SOCIAL" ]; then
    echo "FEHLER: $TVO_SOCIAL nicht gefunden - venv eingerichtet? (python -m venv .venv && pip install -e .)" >&2
    exit 1
fi

echo "== TV Oberwil Social: Resultate generieren =="
echo "(nur 'results' - Ankündigungen/Story laufen separat über generate_posts.sh)"
echo

if [ -d "output/results" ] && [ -n "$(find output/results -name '*.png' -print -quit 2>/dev/null)" ]; then
    echo "Hinweis: bestehende Bilder in output/results/ werden überschrieben (gleicher Wochenordner + Dateiname)."
    echo
fi

RESULTS_LOG=$(mktemp)
trap 'rm -f "$RESULTS_LOG"' EXIT

echo "--- tvo-social results (letztes abgeschlossenes Wochenende) ---"
if ! "$TVO_SOCIAL" results | tee "$RESULTS_LOG"; then
    echo >&2
    echo "FEHLER: 'tvo-social results' ist fehlgeschlagen. Abbruch." >&2
    exit 1
fi
echo

RESULTS_COUNT=$(find output/results -name '*.png' 2>/dev/null | wc -l | tr -d ' ')

echo "=================================================="
echo "Zusammenfassung"
echo "=================================================="
echo "Resultate-Bilder erzeugt: $RESULTS_COUNT Bild(er)"
echo

MISSING_LINES=$(grep -h "FEHLENDES RESULTAT:" "$RESULTS_LOG" 2>/dev/null | sort -u)
if [ -n "$MISSING_LINES" ]; then
    echo "⚠ Spiele ohne Resultat (vor dem Posten prüfen):"
    echo "$MISSING_LINES"
else
    echo "Keine fehlenden Resultate."
fi
echo

echo "Bilder liegen unter:"
echo "  $(pwd)/output/results/<Woche>/post_XofY.png"
