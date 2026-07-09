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

DOCTOR_ARGS=""
for arg in "$@"; do
  case "$arg" in
    --server|--cursor)
      DOCTOR_ARGS="$DOCTOR_ARGS $arg"
      ;;
    *)
      printf 'Unknown argument: %s\n' "$arg" >&2
      exit 2
      ;;
  esac
done

# shellcheck disable=SC2086
"$PYTHON" -m app.tools.doctor $DOCTOR_ARGS
