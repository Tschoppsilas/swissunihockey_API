#!/usr/bin/env bash
# Generates all TV Oberwil Instagram announcement images for the current
# half-season: home-tournament feed posts + full-weekend story posts.
#
# Run this roughly once per half-season, and again whenever game schedules
# have been updated (e.g. venues assigned closer to the date) and you want
# fresh images. `results` is deliberately NOT run here - that flow is
# currently paused.
#
# Usage: ./generate_posts.sh   (run from anywhere - it cd's to its own folder)

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

echo "== TV Oberwil Social: Ankündigungen generieren =="
echo "(results wird bewusst NICHT ausgeführt - aktuell pausiert)"
echo

for dir in output/announcements output/story; do
    if [ -d "$dir" ] && [ -n "$(find "$dir" -name '*.png' -print -quit 2>/dev/null)" ]; then
        echo "Hinweis: bestehende Bilder in $dir/ werden überschrieben (gleicher Wochenordner + Dateiname)."
    fi
done
echo

ANNOUNCE_LOG=$(mktemp)
STORY_LOG=$(mktemp)
trap 'rm -f "$ANNOUNCE_LOG" "$STORY_LOG"' EXIT

echo "--- tvo-social announce (Heimspiel-Feed-Posts) ---"
if ! "$TVO_SOCIAL" announce | tee "$ANNOUNCE_LOG"; then
    echo >&2
    echo "FEHLER: 'tvo-social announce' ist fehlgeschlagen. Abbruch - 'story' wird nicht ausgeführt." >&2
    exit 1
fi
echo

echo "--- tvo-social story (alle Spiele) ---"
if ! "$TVO_SOCIAL" story | tee "$STORY_LOG"; then
    echo >&2
    echo "FEHLER: 'tvo-social story' ist fehlgeschlagen. Abbruch." >&2
    exit 1
fi
echo

ANNOUNCE_COUNT=$(find output/announcements -name '*.png' 2>/dev/null | wc -l | tr -d ' ')
STORY_COUNT=$(find output/story -name '*.png' 2>/dev/null | wc -l | tr -d ' ')

echo "=================================================="
echo "Zusammenfassung"
echo "=================================================="
echo "Heimspiel-Feed-Posts erzeugt: $ANNOUNCE_COUNT Bild(er)"
echo "Story-Bilder erzeugt:         $STORY_COUNT Bild(er)"
echo

MISSING_LINES=$(grep -h "FEHLENDE HALLE:" "$ANNOUNCE_LOG" "$STORY_LOG" 2>/dev/null | sort -u)
if [ -n "$MISSING_LINES" ]; then
    echo "⚠ Spiele ohne Hallen-Zuweisung (vor dem Posten prüfen):"
    echo "$MISSING_LINES"
else
    echo "Keine fehlenden Hallen-Zuweisungen."
fi
echo

echo "Bilder liegen unter:"
echo "  $(pwd)/output/announcements/<Woche>/post_XofY.png"
echo "  $(pwd)/output/story/<Woche>/post_XofY.png"
