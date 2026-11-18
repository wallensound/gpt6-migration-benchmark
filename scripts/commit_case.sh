#!/usr/bin/env bash
# usage: scripts/commit_case.sh <case-folder> "<message>"
set -e
f="$1"; shift
git add "cases/$f" "data/open/$f" "data/sealed/$f" "data/manifests/$f.json" data/MANIFEST.json data/stats/$f* data/leak/$f* runs/P3/$f* runs/prompts runs/sealed_access.log PROGRESS.md scripts 2>/dev/null || true
git commit -qm "$*

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git log --oneline | head -1
