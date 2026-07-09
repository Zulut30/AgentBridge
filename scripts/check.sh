#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

if [ -x ./.venv/bin/python ]; then
  PYTHON="./.venv/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi

"$PYTHON" -m unittest discover -s tests

FILES=$(find . -path './.venv' -prune -o -name '*.py' -print)
"$PYTHON" -m py_compile $FILES

if [ "${1:-}" = "--server" ]; then
  "$PYTHON" -m app.tools.doctor --server
else
  "$PYTHON" -m app.tools.doctor
fi
