from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from sqlmodel import Session, select

from app.config import Settings
from app.core.security import is_ignored_path
from app.core.version import PIPELINE_VERSION, SCHEMA_VERSION
from app.db.models import Document, ExtractionResult, ValidationResult, utcnow
from app.db.session import get_engine
from app.extraction.pipeline import PipelineService
from app.models.schema import ExtractedPolicy

logger = logging.getLogger(__name__)


def sample_policy_dirs() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[3]
    return [
        Path("/app/sample_policies"),
        repo_root / "data" / "sample_policies",
    ]


def sample_output_dirs() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[3]
    return [
        Path("/app/sample_outputs"),
        repo_root / "outputs" / "sample",
    ]


def _safe_stem(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._\-]+", "_", Path(name).stem)[:120]


def _find_sample_json(stem: str, output_dirs: list[Path]) -> Path | None:
    candidates = [
        f"{stem}.json",
        f"{_safe_stem(stem)}.json",
    ]
    for out_dir in output_dirs:
        if not out_dir.is_dir():
            continue
        for name in candidates:
            path = out_dir / name
            if path.is_file():
                return path
        # Fuzzy: compare safe stems
        target = _safe_stem(stem).lower()
        for path in sorted(out_dir.glob("*.json")):
            if _safe_stem(path.stem).lower() == target:
                return path
    return None


def _persist_payload(session: Session, document: Document, payload: dict) -> None:
    policy = ExtractedPolicy.model_validate(payload)
    # Keep source filename aligned with the uploaded document.
    policy.extraction_metadata.source_file = document.filename
    dumped = policy.model_dump(mode="json")

    existing = session.exec(
        select(ExtractionResult).where(ExtractionResult.document_id == document.id)
    ).first()
    if existing:
        existing.payload = dumped
        existing.overall_confidence = float(policy.validation.overall_confidence or 0.0)
        existing.updated_at = utcnow()
        session.add(existing)
    else:
        session.add(
            ExtractionResult(
                document_id=document.id,
                schema_version=SCHEMA_VERSION,
                pipeline_version=PIPELINE_VERSION,
                payload=dumped,
                overall_confidence=float(policy.validation.overall_confidence or 0.0),
            )
        )

    vr = session.exec(
        select(ValidationResult).where(ValidationResult.document_id == document.id)
    ).first()
    summary = policy.validation.model_dump()
    if vr:
        vr.summary = summary
        session.add(vr)
    else:
        session.add(ValidationResult(document_id=document.id, summary=summary))

    document.extraction_status = "extracted"
    document.status = "extracted"
    document.neo4j_status = "local_synced"
    document.error_message = None
    document.updated_at = utcnow()
    session.add(document)
    session.commit()


async def seed_sample_policies_if_empty(settings: Settings) -> None:
    """When the DB is empty, load bundled PDFs + published sample QMS JSON (no live LLM required)."""
    if not settings.auto_seed_samples:
        return

    sample_dir = next((p for p in sample_policy_dirs() if p.is_dir()), None)
    if sample_dir is None:
        logger.warning("auto_seed skipped: sample_policies directory not found")
        return
    output_dirs = sample_output_dirs()

    with Session(get_engine(settings)) as session:
        if session.exec(select(Document)).first() is not None:
            return

    pdfs = sorted(p for p in sample_dir.rglob("*.pdf") if p.is_file() and not is_ignored_path(p))
    if not pdfs:
        logger.warning("auto_seed skipped: no PDFs in %s", sample_dir)
        return

    logger.info("auto_seed starting from %s (%s PDFs)", sample_dir, len(pdfs))
    for path in pdfs:
        try:
            with Session(get_engine(settings)) as session:
                pipeline = PipelineService(settings, session)
                doc = pipeline.save_upload(path.read_bytes(), path.name)
                if doc.status == "duplicate" and doc.duplicate_of:
                    logger.info("auto_seed duplicate %s -> %s", path.name, doc.duplicate_of)
                    continue

                # Parse + index locally (hash embeddings) so Evidence / pages work.
                await pipeline.process_document(doc.id, reprocess=True)
                session.refresh(doc)

                json_path = _find_sample_json(path.stem, output_dirs)
                if json_path is None:
                    logger.warning("auto_seed missing JSON for %s — leaving processed only", path.name)
                    continue

                payload = json.loads(json_path.read_text(encoding="utf-8"))
                _persist_payload(session, doc, payload)
                logger.info("auto_seed complete %s id=%s from %s", path.name, doc.id, json_path.name)
        except Exception:
            logger.exception("auto_seed failed for %s", path.name)
