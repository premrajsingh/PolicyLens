# Render + Neo4j Aura — 60-minute manager demo

Goal: live PolicyLens on Render with Groq + HF + Pinecone + **Neo4j Aura** (not Docker).

---

## RIGHT NOW — Step A: Neo4j Aura account (you)

1. Open: https://neo4j.com/cloud/aura-free/
2. **Start Free** → Google/GitHub/email se sign up
3. Create instance:
   - Name: `policylens`
   - Type: **AuraDB Free**
4. Download / copy credentials popup (sirf ek baar dikhta hai):
   - **NEO4J_URI** = `neo4j+s://xxxx.databases.neo4j.io`
   - **NEO4J_USERNAME** = `neo4j`
   - **NEO4J_PASSWORD** = (generated)
5. Yahan paste karo (URI + password) — main `.env` update kar dunga

Browser query: Aura console → **Open** → Query / Bloom se nodes dikhenge.

---

## Step B: GitHub repo (required for Render)

```bash
cd ~/Desktop/ai
git init   # if needed
# ensure .env is NOT committed (.gitignore already has .env)
git add .
git commit -m "PolicyLens deployment ready"
# create public/private repo on GitHub, then:
git remote add origin https://github.com/YOUR_USER/policylens.git
git push -u origin main
```

---

## Step C: Render deploy

1. https://dashboard.render.com → sign up (GitHub)
2. **New** → **Blueprint** → select `policylens` repo (`render.yaml`)
   - OR create two services manually:
     - **Web Service** (Docker) → root Dockerfile → `policylens-api`
     - **Static Site** → `frontend/` → build `npm ci && npm run build` → publish `dist`
3. Set environment variables on **API** service (Dashboard → Environment):

| Key | Value |
|-----|--------|
| `GROQ_API_KEY` | your gsk_… |
| `HF_TOKEN` | your hf_… |
| `PINECONE_API_KEY` | your pcsk_… |
| `PINECONE_INDEX_NAME` | `policylens` |
| `PINECONE_DIMENSION` | `384` |
| `VECTOR_STORE` | `pinecone` |
| `VECTOR_NAMESPACE` | `policylens-production` |
| `LLM_PROVIDER` | `groq` |
| `LLM_MODEL` | `openai/gpt-oss-20b` |
| `EMBEDDING_PROVIDER` | `huggingface` |
| `GRAPH_STORE` | `neo4j` |
| `NEO4J_URI` | `neo4j+s://….databases.neo4j.io` |
| `NEO4J_USERNAME` | `neo4j` |
| `NEO4J_PASSWORD` | Aura password |
| `NEO4J_DATABASE` | `neo4j` |
| `ALLOWED_ORIGINS` | `https://policylens-web.onrender.com` (your static URL) |
| `FRONTEND_URL` | same static URL |
| `OCR_ENABLED` | `false` |

4. On **Static** service set:

| Key | Value |
|-----|--------|
| `VITE_API_BASE_URL` | `https://policylens-api.onrender.com` (your API URL, no trailing slash) |

5. Deploy → wait ~5–10 min (free tier cold start)

6. Open static URL → Settings should show all providers configured  
7. Upload 1 sample PDF → Process → Extract → show manager

---

## Manager talking points

- Standalone PolicyLens (not Protrac)
- Groq LLM (free) + HF embeddings (free) + Pinecone vectors + Neo4j Aura graph
- Evidence-backed QMS JSON; Neo4j = explainability layer
- Free-tier rate limits may slow batch extract

---

## Local Docker Neo4j vs Aura

| | Local Docker | Aura Free |
|--|--------------|-----------|
| Account | No | Yes |
| Render | No | Yes |
| Nodes UI | localhost:7474 | Aura console |

For manager **Render demo**, use **Aura** only.
