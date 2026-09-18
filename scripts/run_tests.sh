#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
# shellcheck disable=SC1091
source .venv/bin/activate
export PYTHONPATH="$ROOT/backend"
ruff format app tests
ruff check app tests
mypy app || true
pytest -q
cd "$ROOT/frontend"
npm test -- --run || true
npm run build
