# Test Plan

## Unit

- PDF / `__MACOSX` / `._` filtering
- SHA-256 hashing & duplicate detection
- Page extraction & table metadata
- OCR fallback decision
- Chunking & chunk metadata
- Document isolation in retrieval
- Currency / percentage / duration / date / status normalization
- Schema validation & evidence validation
- Missing evidence ? null + unknown
- Conflict detection
- Malformed LLM output handling
- MockLLM no-hallucination behavior
- Local vector/graph stores
- Pinecone/Neo4j adapters with mocks (filters, missing config, healthcheck, parameterized Cypher, duplicate prevention)

## Integration / API

- Upload, process, extract, JSON download, graph, compare, provider health
- httpx AsyncClient against FastAPI TestClient

## Frontend

- Vitest unit smoke
- `npm run build` production build

## Evals

- `evals/run_evals.py` measures schema validity, evidence coverage, review/conflict/hallucination counts
- No accuracy claims without measured results

## Verification script order

1. ruff format/check
2. mypy (configured modules)
3. pytest
4. frontend build
5. health endpoints
6. sample extraction + JSON validate
