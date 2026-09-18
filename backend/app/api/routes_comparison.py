from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.core.errors import AppError
from app.db.models import ExtractionResult
from app.db.session import get_session

router = APIRouter(tags=["comparison"])


class CompareRequest(BaseModel):
    first_document_id: str
    second_document_id: str


def _flatten(payload: dict, prefix: str = "") -> dict[str, dict]:
    out: dict[str, dict] = {}
    if isinstance(payload, dict):
        if "status" in payload and "evidence" in payload:
            out[prefix] = payload
            return out
        for k, v in payload.items():
            if k in {
                "extraction_metadata",
                "validation",
                "document",
                "schema_version",
                "pipeline_version",
            }:
                continue
            path = f"{prefix}.{k}" if prefix else k
            out.update(_flatten(v, path))
    return out


@router.post("/api/compare")
async def compare(
    body: CompareRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    if body.first_document_id == body.second_document_id:
        raise AppError("Select two different policies", status_code=400)
    a = session.exec(
        select(ExtractionResult).where(ExtractionResult.document_id == body.first_document_id)
    ).first()
    b = session.exec(
        select(ExtractionResult).where(ExtractionResult.document_id == body.second_document_id)
    ).first()
    if not a or not b:
        raise AppError("Both documents must be extracted before comparison", status_code=400)

    fa, fb = _flatten(a.payload), _flatten(b.payload)
    keys = sorted(set(fa) | set(fb))
    differences = []
    for key in keys:
        left = fa.get(key)
        right = fb.get(key)
        if any(
            (left or {}).get(k) != (right or {}).get(k)
            for k in ("normalized_value", "status", "conditions", "conflicts")
        ):
            differences.append(
                {
                    "field_path": key,
                    "first": left,
                    "second": right,
                }
            )

    from app.providers.graph_store.factory import create_graph_store

    try:
        graph_compare = await create_graph_store(settings).compare_policies(
            body.first_document_id, body.second_document_id
        )
    except Exception:
        graph_compare = {"available": False}
    return {
        "first_document_id": body.first_document_id,
        "second_document_id": body.second_document_id,
        "difference_count": len(differences),
        "differences": differences,
        "graph_compare": graph_compare,
    }
