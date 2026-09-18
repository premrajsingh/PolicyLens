from __future__ import annotations

import hashlib
import logging
from typing import Any

from app.models.schema import HealthStatus
from app.providers.vector_store.base import Chunk, RetrievedChunk

logger = logging.getLogger(__name__)


class PineconeVectorStore:
    """Official Pinecone SDK adapter. Never silently falls back to local."""

    def __init__(
        self,
        *,
        api_key: str,
        index_name: str,
        namespace: str,
        dimension: int,
        cloud: str = "aws",
        region: str = "us-east-1",
    ) -> None:
        if not api_key:
            raise ValueError("PINECONE_API_KEY is required when VECTOR_STORE=pinecone")
        from pinecone import Pinecone

        self._pc = Pinecone(api_key=api_key)
        self.index_name = index_name
        self.namespace = namespace
        self.dimension = dimension
        self.cloud = cloud
        self.region = region
        self._index = self._pc.Index(index_name)

    def _meta(self, chunk: Chunk) -> dict[str, Any]:
        # Keep text short — Pinecone metadata has size limits.
        text_preview = (chunk.text or "")[:900]
        return {
            "document_id": chunk.document_id,
            "source_file": chunk.source_file,
            "page_number": chunk.page_number,
            "section": chunk.section,
            "chunk_id": chunk.chunk_id,
            "chunk_type": chunk.chunk_type,
            "parser": chunk.parser,
            "text": text_preview,
            "text_hash": chunk.text_hash or hashlib.sha256(chunk.text.encode("utf-8")).hexdigest(),
        }

    async def upsert_chunks(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        vectors = []
        for chunk in chunks:
            if chunk.embedding is None:
                raise ValueError(f"Chunk {chunk.chunk_id} missing embedding")
            if len(chunk.embedding) != self.dimension:
                raise ValueError(
                    f"Embedding dim {len(chunk.embedding)} conflicts with PINECONE_DIMENSION="
                    f"{self.dimension}"
                )
            vectors.append(
                {
                    "id": chunk.chunk_id,
                    "values": chunk.embedding,
                    "metadata": self._meta(chunk),
                }
            )
        batch = 100
        upserted = 0
        for i in range(0, len(vectors), batch):
            result = self._index.upsert(vectors=vectors[i : i + batch], namespace=self.namespace)
            upserted += int(getattr(result, "upserted_count", None) or len(vectors[i : i + batch]))
        logger.info(
            "pinecone_upsert_ok index=%s namespace=%s vectors=%s upserted=%s",
            self.index_name,
            self.namespace,
            len(vectors),
            upserted,
        )

    async def search(
        self,
        query: str,
        *,
        document_id: str | None = None,
        section: str | None = None,
        top_k: int = 8,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedChunk]:
        if query_embedding is None:
            raise ValueError("query_embedding is required for Pinecone search")
        filt: dict[str, Any] = {}
        if document_id:
            filt["document_id"] = {"$eq": document_id}
        if section:
            filt["section"] = {"$eq": section}
        result = self._index.query(
            vector=query_embedding,
            top_k=top_k,
            namespace=self.namespace,
            include_metadata=True,
            filter=filt or None,
        )
        matches = getattr(result, "matches", None) or result.get("matches", [])
        out: list[RetrievedChunk] = []
        for match in matches:
            meta = getattr(match, "metadata", None) or match.get("metadata") or {}
            score = float(getattr(match, "score", None) or match.get("score") or 0.0)
            out.append(
                RetrievedChunk(
                    chunk_id=str(meta.get("chunk_id") or getattr(match, "id", "")),
                    document_id=str(meta.get("document_id", "")),
                    source_file=str(meta.get("source_file", "")),
                    page_number=int(meta.get("page_number") or 0),
                    section=str(meta.get("section", "general")),
                    text=str(meta.get("text") or ""),
                    score=score,
                    chunk_type=str(meta.get("chunk_type", "text")),
                    parser=str(meta.get("parser", "text")),
                    text_hash=str(meta.get("text_hash", "")),
                )
            )
        return out

    async def delete_document(self, document_id: str) -> None:
        try:
            self._index.delete(
                filter={"document_id": {"$eq": document_id}},
                namespace=self.namespace,
            )
        except Exception as exc:  # noqa: BLE001
            # Serverless indexes return 404 "Namespace not found" when empty —
            # that must not block the first upsert.
            msg = str(exc).lower()
            if "namespace not found" in msg or "404" in msg:
                logger.info(
                    "pinecone_delete_skip namespace=%s detail=%s",
                    self.namespace,
                    str(exc)[:160],
                )
                return
            raise

    async def healthcheck(self) -> HealthStatus:
        try:
            stats = self._index.describe_index_stats()
            dim = getattr(stats, "dimension", None) or stats.get("dimension")
            if dim is not None and int(dim) != self.dimension:
                return HealthStatus(
                    name="pinecone",
                    status="error",
                    detail=f"Index dimension {dim} != configured {self.dimension}",
                    configured=True,
                )
            total = getattr(stats, "total_vector_count", None)
            if total is None and isinstance(stats, dict):
                total = stats.get("total_vector_count")
            return HealthStatus(
                name="pinecone",
                status="ok",
                detail=(
                    f"index={self.index_name} namespace={self.namespace} "
                    f"vectors={total if total is not None else 'unknown'}"
                ),
                configured=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("pinecone_healthcheck_failed")
            return HealthStatus(
                name="pinecone",
                status="error",
                detail=str(exc)[:300],
                configured=True,
            )
