#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  PYTHON="python"
fi

"$PYTHON" -m venv .venv
. ./.venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
fi

if [ ! -f agentbridge.yaml ]; then
  cp examples/agentbridge.yaml agentbridge.yaml
fi

python -m app.tools.doctor

printf "\nAgentBridge installed.\n"
printf "Run: ./scripts/run.sh\n"
printf "Check: ./scripts/check.sh\n"
