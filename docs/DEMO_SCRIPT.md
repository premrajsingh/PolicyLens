# Demo Script (Evaluator)

## 1. Offline start (no paid APIs)

```bash
cd /path/to/policylens
cp .env.example .env
# ensure VECTOR_STORE=local GRAPH_STORE=local LLM_PROVIDER=mock

cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
../scripts/start_backend.sh
```

In another terminal:

```bash
cd frontend && npm install && ../scripts/start_frontend.sh
```

Open http://localhost:5173

## 2. Health

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/providers/health
```

Confirm mock LLM + local vector/graph are `ok`.

## 3. Policies

1. Go to **Policies**
2. Drag-drop PDFs from `data/sample_policies/`
3. Observe duplicate detection for Liberty / Net Catalyst
4. Processing starts automatically after upload (or use **Retry** / **Reprocess from scratch**)
5. Confirm page count, OCR badge (if any), indexing status

## 4. Extraction workspace

1. Open **Extraction** (Workspace), select a processed document
2. Click **Extract policy** if needed
3. Inspect sections: Insurer & TPA, Policy details, Policy Structure, Demographics, Room & Hospitalization, Maternity, Waiting Periods, Other Benefits, Infertility & Ambulance, Buffer & Waivers, Evidence, QMS JSON
4. Confirm non-null values (if any) show page quotes; otherwise `unknown`

## 5. Comparison

1. Extract two distinct policies
2. Open **Compare**, select both
3. Review highlighted field differences with evidence

## 6. Batch CLI outputs

```bash
./scripts/run_sample_extraction.sh
./scripts/run_evals.sh
ls outputs/sample/
```

## 7. Optional live Pinecone / Neo4j / OpenAI

Edit `.env`:

```
LLM_PROVIDER=openai
OPENAI_API_KEY=...
LLM_MODEL=gpt-4o-mini
VECTOR_STORE=pinecone
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=policylens
PINECONE_DIMENSION=384
GRAPH_STORE=neo4j
NEO4J_PASSWORD=...
```

Re-run healthcheck — misconfiguration must error, not silently fall back.

## Talking points

- Standalone PolicyLens project; Protrac not required
- QMS JSON is authoritative; Neo4j is explainability
- Evidence-backed extraction with conflict detection
- No hardcoded answers from sample PDFs
