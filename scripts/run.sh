#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8787}"

if [ -x ./.venv/bin/python ]; then
  PYTHON="./.venv/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi

"$PYTHON" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
