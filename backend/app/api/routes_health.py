from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.core.version import APP_NAME, APP_SUBTITLE, PIPELINE_VERSION, SCHEMA_VERSION
from app.db.session import get_session
from app.models.schema import HealthStatus
from app.providers.embeddings.provider import create_embedding_provider
from app.providers.graph_store.factory import create_graph_store
from app.providers.llm.provider import create_llm_provider
from app.providers.vector_store.factory import create_vector_store

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": APP_NAME,
        "subtitle": APP_SUBTITLE,
        "schema_version": SCHEMA_VERSION,
        "pipeline_version": PIPELINE_VERSION,
    }


@router.get("/api/version")
def version() -> dict:
    return {
        "app": APP_NAME,
        "subtitle": APP_SUBTITLE,
        "schema_version": SCHEMA_VERSION,
        "pipeline_version": PIPELINE_VERSION,
    }


@router.get("/api/providers/health")
async def providers_health(
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> dict:
    results: list[HealthStatus] = []
    # LLM
    try:
        llm = create_llm_provider(settings)
        results.append(await llm.healthcheck())
    except Exception as exc:  # noqa: BLE001
        results.append(
            HealthStatus(name="llm", status="error", detail=str(exc)[:300], configured=False)
        )
    # Embeddings
    try:
        emb = create_embedding_provider(settings)
        info = emb.healthcheck()
        results.append(
            HealthStatus(
                name=str(info.get("name", "embeddings")),
                status=str(info.get("status", "ok")),  # type: ignore[arg-type]
                detail=str(info),
                configured=True,
            )
        )
    except Exception as exc:  # noqa: BLE001
        results.append(
            HealthStatus(name="embeddings", status="error", detail=str(exc)[:300], configured=False)
        )
    # Vector
    try:
        vs = create_vector_store(settings)
        results.append(await vs.healthcheck())
    except Exception as exc:  # noqa: BLE001
        results.append(
            HealthStatus(
                name="vector_store",
                status="error",
                detail=str(exc)[:300],
                configured=settings.vector_store == "pinecone",
            )
        )
    # Graph
    try:
        gs = create_graph_store(settings)
        results.append(await gs.healthcheck())
    except Exception as exc:  # noqa: BLE001
        results.append(
            HealthStatus(
                name="graph_store",
                status="error",
                detail=str(exc)[:300],
                configured=settings.graph_store == "neo4j",
            )
        )

    _ = session  # ensure DB dependency works
    settings_info = {
        "llm_provider": settings.llm_provider,
        "embedding_provider": settings.embedding_provider,
        "vector_store": settings.vector_store,
        "graph_store": settings.graph_store,
        "ocr_enabled": settings.ocr_enabled,
        "openai_configured": bool(settings.openai_api_key),
        "gemini_configured": bool(settings.gemini_api_key),
        "groq_configured": bool(settings.groq_api_key),
        "huggingface_configured": bool(settings.hf_token),
        "pinecone_configured": bool(settings.pinecone_api_key),
        "neo4j_configured": bool(settings.neo4j_password),
        "data_dir": str(settings.data_dir),
        "output_dir": str(settings.output_dir),
    }
    overall = "ok" if all(r.status in {"ok", "disabled"} for r in results) else "degraded"
    return {
        "status": overall,
        "providers": [r.model_dump() for r in results],
        "settings": settings_info,
    }


@router.get("/api/dashboard")
def dashboard(session: Session = Depends(get_session)) -> dict:
    from app.db.models import Document, ExtractionResult

    docs = session.exec(select(Document).where(Document.duplicate_of == None)).all()  # noqa: E711
    ids = {d.id for d in docs}
    extractions = [e for e in session.exec(select(ExtractionResult)).all() if e.document_id in ids]
    by_id = {e.document_id: e for e in extractions}
    processed = [d for d in docs if d.status in {"processed", "extracted"}]
    confidences = [e.overall_confidence for e in extractions]
    review = 0
    for e in extractions:
        review += int((e.payload.get("validation") or {}).get("fields_requiring_review") or 0)
    return {
        "total_documents": len(docs),
        "fields_found": sum(
            int(e.payload.get("validation", {}).get("fields_found", 0)) for e in extractions
        ),
        "fields_missing": sum(
            int(e.payload.get("validation", {}).get("fields_missing", 0)) for e in extractions
        ),
        "evidence_coverage": sum(
            float(e.payload.get("validation", {}).get("evidence_coverage", 0)) for e in extractions
        )
        / len(extractions)
        if extractions
        else 0,
        "processing_documents": sum(d.status in {"processing", "queued", "uploaded"} for d in docs),
        "processed_documents": len(processed),
        "extracted_policies": len(extractions),
        "average_confidence": (sum(confidences) / len(confidences)) if confidences else 0.0,
        "fields_requiring_review": review,
        "recent": [
            {
                "id": d.id,
                "filename": d.original_filename or d.filename,
                "status": d.status,
                "created_at": d.created_at.isoformat(),
                "page_count": d.page_count,
                "insurer": by_id[d.id].payload.get("insurer", {}).get("value")
                if d.id in by_id
                else None,
                "policy_type": by_id[d.id].payload.get("policy_type", {}).get("value")
                if d.id in by_id
                else None,
                "fields_found": by_id[d.id].payload.get("validation", {}).get("fields_found", 0)
                if d.id in by_id
                else 0,
                "fields_missing": by_id[d.id].payload.get("validation", {}).get("fields_missing", 0)
                if d.id in by_id
                else 0,
                "review_count": by_id[d.id]
                .payload.get("validation", {})
                .get("fields_requiring_review", 0)
                if d.id in by_id
                else 0,
            }
            for d in sorted(docs, key=lambda x: x.created_at, reverse=True)[:10]
        ],
    }
