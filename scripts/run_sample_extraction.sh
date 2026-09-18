#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
# shellcheck disable=SC1091
source .venv/bin/activate
export PYTHONPATH="$ROOT/backend"
python -m app.cli extract-all --input-dir "$ROOT/data/sample_policies" --output-dir "$ROOT/outputs/sample"
python -m app.cli validate-output --path "$ROOT/outputs/sample"
