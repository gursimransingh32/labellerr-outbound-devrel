#!/usr/bin/env bash
# Runs the full pipeline: refresh Labellerr pages -> do-not-contact check -> score -> drafts.
# Usage: bash run.sh [step] [--offline] [--as-of YYYY-MM-DD]
#   bash run.sh                          # everything, live check of Labellerr's site
#   bash run.sh --offline                # no network: cached pages + committed snapshot
#   bash run.sh score --as-of 2026-09-28 # just the ranking, for a fixed date
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found. Run: bash setup.sh" >&2
  exit 1
fi

python3 src/outbound.py "$@"
