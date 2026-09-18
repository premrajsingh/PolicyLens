# Pinecone Design

## Configuration

```env
VECTOR_STORE=pinecone
VECTOR_NAMESPACE=policylens-development
PINECONE_API_KEY=
PINECONE_INDEX_NAME=policylens
PINECONE_CLOUD=aws
PINECONE_REGION=us-east-1
PINECONE_DIMENSION=384
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

Dimension must match the embedding model. Mismatch fails healthcheck/upsert with a clear error.

## Vector ID

Deterministic: `{document_id}-page-{page_number}-chunk-{chunk_index}`

## Metadata (no full sensitive body text)

```json
{
  "document_id": "...",
  "source_file": "GHI Policy.pdf",
  "page_number": 8,
  "section": "maternity",
  "chunk_id": "...",
  "chunk_type": "text",
  "parser": "text",
  "text_hash": "sha256..."
}
```

Source text remains in SQLite; retrieval rehydrates from `chunk_id`.

## Filters

```json
{ "document_id": { "$eq": "document-id" } }
```

Optional section filter when searching field groups.

## Behavior

- Idempotent upserts
- Delete by document_id metadata filter
- Explicit pinecone mode: configuration/connection errors surface; no silent local fallback
- LocalVectorStore used when `VECTOR_STORE=local`
