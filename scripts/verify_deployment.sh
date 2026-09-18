#!/usr/bin/env bash
# Verify deployment-ready configuration without printing secrets.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ok=0
fail=0
warn() { echo "WARN  $*"; }
pass() { echo "OK    $*"; ok=$((ok+1)); }
bad()  { echo "FAIL  $*"; fail=$((fail+1)); }

echo "=== PolicyLens deployment readiness ==="

if command -v tesseract >/dev/null 2>&1; then
  pass "tesseract $(tesseract --version 2>&1 | head -1)"
else
  bad "tesseract missing — brew install tesseract"
fi

if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    pass "docker daemon running"
    if docker compose ps --status running 2>/dev/null | grep -q neo4j; then
      pass "neo4j container running"
    else
      warn "neo4j not running — ./scripts/start_neo4j.sh"
    fi
  else
    bad "docker installed but daemon not running — open Docker Desktop"
  fi
else
  bad "docker missing — install Docker Desktop, then ./scripts/start_neo4j.sh"
fi

ENV_FILE="$ROOT/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  bad ".env missing — cp .env.example .env and fill keys"
else
  get() { grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'"; }
  require_nonempty() {
    local k="$1" v
    v="$(get "$k")"
    if [[ -n "$v" && "$v" != gsk_... && "$v" != hf_... ]]; then
      pass "$k is set"
    else
      bad "$k is empty — see docs/DEPLOYMENT_SETUP.md"
    fi
  }
  [[ "$(get LLM_PROVIDER)" == "groq" ]] && pass "LLM_PROVIDER=groq" || bad "LLM_PROVIDER should be groq"
  [[ "$(get EMBEDDING_PROVIDER)" == "huggingface" ]] && pass "EMBEDDING_PROVIDER=huggingface" || bad "EMBEDDING_PROVIDER should be huggingface"
  [[ "$(get VECTOR_STORE)" == "pinecone" ]] && pass "VECTOR_STORE=pinecone" || bad "VECTOR_STORE should be pinecone"
  [[ "$(get GRAPH_STORE)" == "neo4j" ]] && pass "GRAPH_STORE=neo4j" || bad "GRAPH_STORE should be neo4j"
  require_nonempty GROQ_API_KEY
  require_nonempty HF_TOKEN
  require_nonempty PINECONE_API_KEY
  require_nonempty NEO4J_PASSWORD
  [[ "$(get PINECONE_DIMENSION)" == "384" ]] && pass "PINECONE_DIMENSION=384" || bad "PINECONE_DIMENSION must be 384"
fi

if curl -sf http://127.0.0.1:8000/api/providers/health >/tmp/policylens_health.json 2>/dev/null; then
  pass "API /api/providers/health reachable"
  python3 - <<'PY'
import json
data=json.load(open("/tmp/policylens_health.json"))
for p in data.get("providers", []):
    status=p.get("status")
    name=p.get("name")
    print(f"  provider {name}: {status}")
PY
else
  warn "API not running — start with ./scripts/start_backend.sh after .env is filled"
fi

echo "=== summary: $ok checks passed, $fail failures ==="
[[ "$fail" -eq 0 ]] || exit 1
