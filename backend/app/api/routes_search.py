from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.config import Settings, get_settings
from app.core.errors import AppError
from app.db.models import Document
from app.db.session import get_session
from app.providers.embeddings.provider import create_embedding_provider
from app.providers.vector_store.factory import create_vector_store
from app.retrieval.hybrid import hybrid_search

router = APIRouter(tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    document_id: str | None = None
    section: str | None = None
    top_k: int = Field(default=8, ge=1, le=50)


@router.post("/api/search")
async def search(
    body: SearchRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    if body.document_id:
        doc = session.get(Document, body.document_id)
        if not doc:
            raise AppError("Document not found", status_code=404, code="not_found")
        source_file = doc.filename
    else:
        source_file = ""
    vector_store = create_vector_store(settings)
    embedder = create_embedding_provider(settings)
    results = await hybrid_search(
        session,
        vector_store,
        embedder,
        query=body.query,
        document_id=body.document_id,
        section=body.section,
        top_k=body.top_k,
        source_file=source_file,
    )
    return {
        "query": body.query,
        "results": [
            {
                "chunk_id": r.chunk_id,
                "document_id": r.document_id,
                "source_file": r.source_file,
                "page_number": r.page_number,
                "section": r.section,
                "score": r.score,
                "parser": r.parser,
                "text": r.text[:1000],
            }
            for r in results
        ],
    }
