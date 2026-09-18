from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.core.errors import AppError
from app.db.models import Document, ExtractionResult, ValidationResult
from app.db.session import get_session
from app.extraction.pipeline import PipelineService

router = APIRouter(tags=["policies"])


def _get_payload(session: Session, document_id: str) -> dict:
    row = session.exec(
        select(ExtractionResult).where(ExtractionResult.document_id == document_id)
    ).first()
    if not row:
        raise AppError("Extraction not found", status_code=404, code="not_found")
    return row.payload


@router.post("/api/policies/{document_id}/extract")
def extract_policy(
    document_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    doc = session.get(Document, document_id)
    if not doc:
        raise AppError("Document not found", status_code=404, code="not_found")
    pipeline = PipelineService(settings, session)
    try:
        policy = asyncio.run(pipeline.extract_policy(document_id))
    except ValueError as exc:
        raise AppError(str(exc), status_code=400, code="extract_error") from exc
    return policy.model_dump(mode="json")


@router.get("/api/policies/{document_id}/extraction")
def get_extraction(document_id: str, session: Session = Depends(get_session)) -> dict:
    return _get_payload(session, document_id)


@router.get("/api/policies/{document_id}/json")
def get_json(document_id: str, session: Session = Depends(get_session)) -> dict:
    return _get_payload(session, document_id)


@router.get("/api/policies/{document_id}/download")
def download_json(document_id: str, session: Session = Depends(get_session)) -> PlainTextResponse:
    payload = _get_payload(session, document_id)
    body = json.dumps(payload, indent=2)
    filename = f"{document_id}.json"
    return PlainTextResponse(
        body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/policies/{document_id}/evidence")
def get_evidence(document_id: str, session: Session = Depends(get_session)) -> dict:
    payload = _get_payload(session, document_id)
    items = []

    def walk(obj, prefix=""):
        if isinstance(obj, dict):
            if "evidence" in obj and "status" in obj:
                items.append({"field_path": prefix, **obj})
                return
            for k, v in obj.items():
                walk(v, f"{prefix}.{k}" if prefix else k)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{prefix}[{i}]")

    walk(payload)
    return {"document_id": document_id, "fields": items}


@router.get("/api/policies/{document_id}/validation")
def get_validation(document_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.exec(
        select(ValidationResult).where(ValidationResult.document_id == document_id)
    ).first()
    if not row:
        payload = _get_payload(session, document_id)
        return payload.get("validation") or {}
    return row.summary


@router.get("/api/policies/{document_id}/graph")
async def get_graph(
    document_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    from app.providers.graph_store.factory import create_graph_store

    try:
        return await create_graph_store(settings).get_policy_graph(document_id)
    except Exception:  # noqa: BLE001
        return {
            "policy_id": document_id,
            "nodes": [],
            "relationships": [],
            "available": False,
            "error": "Graph temporarily unavailable",
        }
