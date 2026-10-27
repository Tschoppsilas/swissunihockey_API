#!/usr/bin/env bash
# Generates the TV Oberwil results posts for the current Mon-Sun week (all
# games already played; falls back to the latest week with played games if
# nothing has been played yet this week):
#   - the results story (all categories)       -> output/results/
#   - a feed post with just the home-game results, if there were any
#                                              -> output/home_results/
#
# Run this weekly (e.g. Sunday evening after the last game) - or anytime you
# want to (re)generate the current results. `announce`
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

for dir in output/results output/home_results; do
    if [ -d "$dir" ] && [ -n "$(find "$dir" -name '*.png' -print -quit 2>/dev/null)" ]; then
        echo "Hinweis: bestehende Bilder in $dir/ werden überschrieben (gleicher Wochenordner + Dateiname)."
    fi
done
echo

RESULTS_LOG=$(mktemp)
trap 'rm -f "$RESULTS_LOG"' EXIT

echo "--- tvo-social results (aktuelle Woche) ---"
if ! "$TVO_SOCIAL" results | tee "$RESULTS_LOG"; then
    echo >&2
    echo "FEHLER: 'tvo-social results' ist fehlgeschlagen. Abbruch." >&2
    exit 1
fi
echo

# Counted from this run's own log (not from the folders), so images of older
# weeks that are still lying around aren't included.
STORY_COUNT=$(grep -cE 'geschrieben:.*[/\\]results[/\\]' "$RESULTS_LOG" 2>/dev/null || true)
FEED_COUNT=$(grep -cE 'geschrieben:.*[/\\]home_results[/\\]' "$RESULTS_LOG" 2>/dev/null || true)

echo "=================================================="
echo "Zusammenfassung"
echo "=================================================="
echo "Story-Bilder (Resultate):          $STORY_COUNT Bild(er)"
echo "Feed-Post-Bilder (Heimspiel-Resultate): $FEED_COUNT Bild(er)"
if [ "$FEED_COUNT" = "0" ] && grep -q "Keine Heimspiele in diesem Zeitraum" "$RESULTS_LOG"; then
    echo "  (Keine Heimspiele in diesem Zeitraum)"
fi
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
echo "  Story: $(pwd)/output/results/<Woche>/post_XofY.png"
echo "  Feed:  $(pwd)/output/home_results/<Woche>/post_XofY.png"
