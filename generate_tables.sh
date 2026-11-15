#!/usr/bin/env bash
# Generates the TV Oberwil table posts: one image per league group (all TVO teams
# of a group share one image), for the winter break or the end of the season.
#   -> output/tables/<season>/<league>.png
#
# Usage: ./generate_tables.sh   (run from anywhere - it cd's to its own folder)
#   Optional (passed on to `tvo-social tables`), e.g.
#   ./generate_tables.sh --label Winterpause           ("Stand: <today> - Winterpause" in the image)
#   ./generate_tables.sh --label Schlusstabelle --season 2025
#   ./generate_tables.sh --stand 2026-12-20            (a different 'Stand' date)
#
# Categories listed in config.yaml under tables.exclude_categories are skipped.

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

echo "== TV Oberwil Social: Tabellen generieren =="
echo

if [ -d "output/tables" ] && [ -n "$(find output/tables -name '*.png' -print -quit 2>/dev/null)" ]; then
    echo "Hinweis: bestehende Bilder in output/tables/<Saison>/ werden ueberschrieben (gleiche Saison + gleicher Dateiname)."
    echo
fi

TABLES_LOG=$(mktemp)
trap 'rm -f "$TABLES_LOG"' EXIT

echo "--- tvo-social tables ---"
if ! "$TVO_SOCIAL" tables "$@" | tee "$TABLES_LOG"; then
    echo >&2
    echo "FEHLER: 'tvo-social tables' ist fehlgeschlagen. Abbruch." >&2
    exit 1
fi
echo

# Counted from this run's own log, so images of older runs are not included.
IMAGE_COUNT=$(grep -c 'geschrieben:' "$TABLES_LOG" 2>/dev/null || true)

echo "=================================================="
echo "Zusammenfassung"
echo "=================================================="
echo "Tabellen-Bilder erzeugt: $IMAGE_COUNT Bild(er)"
echo

EXCLUDED_LINES=$(grep -h "ausgeschlossen (Konfiguration)" "$TABLES_LOG" 2>/dev/null | sort -u)
if [ -n "$EXCLUDED_LINES" ]; then
    echo "Ausgeschlossen:"
    echo "$EXCLUDED_LINES" | sed 's/^/  /'
    echo
fi

SKIPPED_LINES=$(grep -h "^UEBERSPRUNGEN:" "$TABLES_LOG" 2>/dev/null | sort -u)
if [ -n "$SKIPPED_LINES" ]; then
    echo "Uebersprungene Tabellen (mit Grund):"
    echo "$SKIPPED_LINES" | sed 's/^UEBERSPRUNGEN: /  /'
else
    echo "Keine Tabellen uebersprungen."
fi
echo

echo "Bilder liegen unter:"
echo "  $(pwd)/output/tables/<Saison>/<Liga>.png"
