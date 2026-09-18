# PolicyLens Backend

FastAPI application for GMC policy ingestion, hybrid retrieval, structured extraction, and QMS JSON export.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

CLI:

```bash
python -m app.cli healthcheck
python -m app.cli ingest --input-dir ../data/sample_policies
python -m app.cli extract-all --input-dir ../data/sample_policies --output-dir ../outputs/sample
```
