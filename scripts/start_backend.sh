#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
export PYTHONPATH="$ROOT/backend"
exec uvicorn app.main:app --host "${APP_HOST:-127.0.0.1}" --port "${APP_PORT:-8000}" --reload
