#!/usr/bin/env bash
# One-time setup: checks Python, prepares folders, runs the unit tests.
# Needs only Python 3.8+ and bash (no pip installs, no API keys).
# Usage: bash setup.sh
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found. Install Python 3.8+ and run: bash setup.sh" >&2
  exit 1
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 8):
    sys.exit("ERROR: Python 3.8+ required, found " + sys.version.split()[0])
print("Python " + sys.version.split()[0] + " OK (standard library only)")
PY

mkdir -p output data/cache
chmod +x setup.sh run.sh src/outbound.py 2>/dev/null || true

echo "Running unit tests..."
python3 -m unittest discover -s tests
echo "Setup complete. Next: bash run.sh   (or: bash run.sh --offline)"
