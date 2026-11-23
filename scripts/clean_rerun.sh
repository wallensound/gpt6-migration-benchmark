#!/usr/bin/env bash
# P7 clean rerun: fresh clone, empty cache, `make reproduce CASE=03` (Luna, seed 11).
# Copies the result back into this repo as runs/P7/reproduce.json.
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${TMPDIR:-/tmp}/gpt6-clean-rerun-$(date +%Y%m%d-%H%M%S)"
git clone -q "$SRC" "$DEST"
cp "$SRC/.env" "$DEST/.env" 2>/dev/null || true      # credentials only; never committed
cd "$DEST"
test ! -e runs/state.sqlite || { echo "cache not empty"; exit 1; }
uv sync --frozen -q
make reproduce CASE=${CASE:-03} TARGET=${TARGET:-gpt-6-luna} SEED=${SEED:-11}
mkdir -p "$SRC/runs/P7"
cp runs/P7/reproduce.json "$SRC/runs/P7/reproduce.json"
cp -r runs/P7/* "$SRC/runs/P7/clean-rerun-copy/" 2>/dev/null || { mkdir -p "$SRC/runs/P7/clean-rerun-copy"; cp -r runs/P7/* "$SRC/runs/P7/clean-rerun-copy/"; }
.venv/Scripts/python -m harness.cli status > "$SRC/runs/P7/clean-rerun-status.txt" || true
echo "clean rerun done in $DEST"
