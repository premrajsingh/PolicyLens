from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any

import numpy as np

from app.models.schema import HealthStatus
from app.providers.vector_store.base import Chunk, RetrievedChunk

_STORE_LOCK = RLock()


class LocalVectorStore:
    """Filesystem-backed vector store for tests and offline development."""

    def __init__(self, root: Path, *, dimension: int = 384) -> None:
        self.root = root
        self.dimension = dimension
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / "index.json"
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self._index_path.exists():
            self._data = json.loads(self._index_path.read_text(encoding="utf-8"))
        else:
            self._data = {}

    def _save(self) -> None:
        fd, name = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle)
            os.replace(name, self._index_path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    async def upsert_chunks(self, chunks: list[Chunk]) -> None:
        with _STORE_LOCK:
            self._load()
            for chunk in chunks:
                if chunk.embedding is None:
                    raise ValueError(f"Chunk {chunk.chunk_id} missing embedding")
                if len(chunk.embedding) != self.dimension:
                    raise ValueError(
                        f"Embedding dimension {len(chunk.embedding)} != configured {self.dimension}"
                    )
                self._data[chunk.chunk_id] = {
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "source_file": chunk.source_file,
                    "page_number": chunk.page_number,
                    "section": chunk.section,
                    "text": chunk.text,
                    "chunk_type": chunk.chunk_type,
                    "parser": chunk.parser,
                    "text_hash": chunk.text_hash
                    or hashlib.sha256(chunk.text.encode("utf-8")).hexdigest(),
                    "embedding": chunk.embedding,
                }
            self._save()

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
            return []
        self._load()
        q = np.array(query_embedding, dtype=float)
        q_norm = np.linalg.norm(q) or 1.0
        scored: list[RetrievedChunk] = []
        for row in self._data.values():
            if document_id and row["document_id"] != document_id:
                continue
            if section and row["section"] != section:
                continue
            vec = np.array(row["embedding"], dtype=float)
            score = float(np.dot(q, vec) / (q_norm * (np.linalg.norm(vec) or 1.0)))
            scored.append(
                RetrievedChunk(
                    chunk_id=row["chunk_id"],
                    document_id=row["document_id"],
                    source_file=row["source_file"],
                    page_number=row["page_number"],
                    section=row["section"],
                    text=row["text"],
                    score=score,
                    chunk_type=row["chunk_type"],
                    parser=row["parser"],
                    text_hash=row["text_hash"],
                )
            )
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    async def delete_document(self, document_id: str) -> None:
        with _STORE_LOCK:
            self._load()
            self._data = {k: v for k, v in self._data.items() if v["document_id"] != document_id}
            self._save()

    async def healthcheck(self) -> HealthStatus:
        return HealthStatus(
            name="local_vector_store",
            status="ok",
            detail=f"{len(self._data)} chunks at {self.root}",
            configured=True,
        )
