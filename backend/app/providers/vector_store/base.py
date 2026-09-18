from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    source_file: str
    page_number: int
    section: str
    text: str
    chunk_type: str = "text"
    parser: str = "text"
    text_hash: str = ""
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    source_file: str
    page_number: int
    section: str
    text: str
    score: float
    chunk_type: str = "text"
    parser: str = "text"
    text_hash: str = ""


class VectorStore(Protocol):
    async def upsert_chunks(self, chunks: list[Chunk]) -> None: ...

    async def search(
        self,
        query: str,
        *,
        document_id: str | None = None,
        section: str | None = None,
        top_k: int = 8,
        query_embedding: list[float] | None = None,
    ) -> list[RetrievedChunk]: ...

    async def delete_document(self, document_id: str) -> None: ...

    async def healthcheck(self) -> Any: ...
