#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
# shellcheck disable=SC1091
source .venv/bin/activate
export PYTHONPATH="$ROOT/backend"
python -m app.cli healthcheck
curl -sf "http://${APP_HOST:-127.0.0.1}:${APP_PORT:-8000}/api/health" || true
curl -sf "http://${APP_HOST:-127.0.0.1}:${APP_PORT:-8000}/api/providers/health" || true
