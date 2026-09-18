# Deployment setup

## Local Docker review

Copy `.env.example` to `.env`, configure the live Groq provider or keep the explicit offline mock profile, and start Docker Desktop with the Compose plugin installed.

```sh
docker compose -f compose.demo.yml up --build -d
curl --fail http://127.0.0.1:8000/api/health
```

The named volume preserves PDFs, SQLite and local vector/graph data. The exposed port is bound to localhost. Stop with `docker compose -f compose.demo.yml down`; omit `--volumes` to preserve data.

## Hosted review

The checked-in Render blueprint uses one paid Starter instance and a persistent 1 GB disk. Review current hosting prices before creating it. Supply the Groq API key; the blueprint generates a Basic-auth password for the `reviewer` user. Store that password privately and use HTTPS. The health route is public; policy data, API docs, JSON and PDF routes require authentication.

The build installs pinned Python dependencies, compiles the frontend and runs as an unprivileged user. SQLite, uploaded files, local embeddings and graph data reside under `/data`. Use exactly one worker and one instance. Processing is an in-process background job; interrupted jobs are marked failed at restart and can be retried. A durable worker queue, Postgres, object storage, user-specific authorization and operational monitoring are future requirements for a multi-user production system.

Verify after provisioning: authenticated upload, extraction, page evidence, JSON download, comparison, delete and restart persistence. Confirm provider connectivity separately; an API key being present is not proof that a provider is reachable. No deployment was performed during this review. Docker build/run and hosted smoke checks remain outstanding because this machine has no running Docker daemon or Compose plugin.

Reference: https://render.com/docs/disks
