# Implementation Plan

## Phases

0. Docs + sample PDF copy (this folder + `data/sample_policies/`)
1. Backend, frontend, adapters, extraction, validation
2. Format, lint, typecheck, tests, health, sample extraction
3. Self-repair on failures
4. FINAL_VERIFICATION, KNOWN_LIMITATIONS, DEMO_SCRIPT

## Locked defaults

| Setting | Tests / offline | Demo `.env.example` |
|---------|-----------------|---------------------|
| `LLM_PROVIDER` | `mock` | `mock` (set openai/gemini for real extract) |
| `VECTOR_STORE` | `local` | `pinecone` |
| `GRAPH_STORE` | `local` | `neo4j` |
| Embeddings | local MiniLM 384-d | same |

## Module build order

1. Config, DB, health APIs
2. Ingestion + OCR
3. Embeddings + vector stores + FTS5 hybrid retrieval
4. Schema + LLM providers + validation
5. Graph stores + remaining APIs + CLI
6. React UI
7. Tests + evals
8. Verification

## Run commands

```bash
# Backend
cd backend && python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example ../.env
# For offline: VECTOR_STORE=local GRAPH_STORE=local LLM_PROVIDER=mock
../scripts/start_backend.sh

# Frontend
cd frontend && npm install && ../scripts/start_frontend.sh

# Batch sample extraction
../scripts/run_sample_extraction.sh

# Tests / evals / health
../scripts/run_tests.sh
../scripts/run_evals.sh
../scripts/healthcheck.sh
```

## Local fallback strategy

- `LocalVectorStore` persists under `data/vector_store/`
- `LocalGraphStore` persists JSON under `data/graph_store/`
- `MockLLMProvider` returns schema-valid unknown fields only (no fabricated policy values)
- When `VECTOR_STORE=pinecone` or `GRAPH_STORE=neo4j`, missing credentials raise clear errors

## Security

- Secrets via env only; never logged or returned by API
- Upload size limit; safe filenames; document-scoped retrieval filters
