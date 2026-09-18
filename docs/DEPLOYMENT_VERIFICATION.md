# Deployment verification status

Date: 2026-09-17

## Code / automated checks (completed)

| Check | Result |
|-------|--------|
| Groq provider + missing-key refusal | Pass |
| Hugging Face embeddings + missing-token refusal | Pass |
| Pinecone / Neo4j missing-config refusal | Pass |
| Backend pytest | **15 passed** |
| `docker-compose.yml` for Neo4j | Present |
| `docs/DEPLOYMENT_SETUP.md` | Present |
| `scripts/verify_deployment.sh` | Present |
| `scripts/start_neo4j.sh` | Present |
| `.env.deployment.example` | Deployment profile template (empty keys) |

## Blocked on this machine (user action required)

1. **API keys not filled** — `.env` still uses mock/local; create Groq, Hugging Face, and Pinecone accounts per `docs/DEPLOYMENT_SETUP.md`, then:
   ```bash
   cp .env.deployment.example .env
   # paste GROQ_API_KEY, HF_TOKEN, PINECONE_API_KEY
   ```
2. **Docker not installed** — install [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/), open it, then:
   ```bash
   ./scripts/start_neo4j.sh
   ```
3. **Tesseract not installed** — a Homebrew install was attempted but failed with **No space left on device**. Free disk space, then:
   ```bash
   brew install tesseract
   ```

## After keys + Docker + Tesseract

```bash
./scripts/verify_deployment.sh
./scripts/start_backend.sh
./scripts/start_frontend.sh
./scripts/run_sample_extraction.sh
./scripts/run_evals.sh
```

Live Pinecone indexing and Groq extraction cannot be completed until the keys and Docker daemon are available on this host.
