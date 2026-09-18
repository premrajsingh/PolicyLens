from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path

from sqlmodel import Session, select

from app.config import Settings
from app.core.version import PIPELINE_VERSION, SCHEMA_VERSION
from app.db.models import Document, ExtractionResult, ValidationResult, utcnow
from app.db.session import get_engine
from app.models.schema import ExtractedPolicy

logger = logging.getLogger(__name__)


def demo_seed_dirs() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[3]
    return [
        Path("/app/demo_seed"),
        repo_root / "data" / "demo_seed",
    ]


def sample_output_dirs() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[3]
    return [
        Path("/app/sample_outputs"),
        repo_root / "outputs" / "sample",
    ]


def _safe_stem(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._\-]+", "_", Path(name).stem)[:120]


def _find_sample_json(filename: str, output_dirs: list[Path] | None = None) -> Path | None:
    stem = Path(filename).stem
    dirs = output_dirs or sample_output_dirs()
    candidates = [f"{stem}.json", f"{_safe_stem(stem)}.json"]
    for out_dir in dirs:
        if not out_dir.is_dir():
            continue
        for name in candidates:
            path = out_dir / name
            if path.is_file():
                return path
        target = _safe_stem(stem).lower()
        for path in sorted(out_dir.glob("*.json")):
            if _safe_stem(path.stem).lower() == target:
                return path
            # Match when live filename is a long OCR export prefix of the sample stem.
            sample = _safe_stem(path.stem).lower()
            if target.startswith(sample[:40]) or sample.startswith(target[:40]):
                return path
    return None


def _persist_payload(session: Session, document: Document, payload: dict) -> None:
    policy = ExtractedPolicy.model_validate(payload)
    if getattr(policy, "document", None) is not None:
        policy.document.filename = document.original_filename or document.filename
        policy.document.document_id = document.id
    if policy.extraction_metadata.completion_status != "complete":
        policy.extraction_metadata.completion_status = "complete"
    policy.extraction_metadata.extraction_errors = []
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


def restore_demo_seed_if_needed(settings: Settings) -> None:
    """Copy pre-built demo DB + PDFs into DATA_DIR when the volume is empty."""
    if not settings.auto_seed_samples:
        return

    settings.ensure_dirs()
    db_path = Path(settings.database_url.removeprefix("sqlite:///"))
    # Render free disk wipe → missing/tiny DB. Keep existing populated DBs.
    if db_path.is_file() and db_path.stat().st_size > 50_000:
        return

    seed_dir = next((p for p in demo_seed_dirs() if (p / "policylens.db").is_file()), None)
    if seed_dir is None:
        logger.warning("auto_seed skipped: demo_seed/policylens.db not found")
        return

    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(seed_dir / "policylens.db", db_path)
        docs_src = seed_dir / "documents"
        if docs_src.is_dir():
            settings.documents_dir.mkdir(parents=True, exist_ok=True)
            for pdf in docs_src.glob("*.pdf"):
                shutil.copy2(pdf, settings.documents_dir / pdf.name)
        vec_src = seed_dir / "vector_store"
        if vec_src.is_dir():
            settings.vector_store_dir.mkdir(parents=True, exist_ok=True)
            for item in vec_src.iterdir():
                if item.is_file():
                    shutil.copy2(item, settings.vector_store_dir / item.name)
        logger.info("auto_seed restored demo library from %s -> %s", seed_dir, db_path)
    except Exception:
        logger.exception("auto_seed failed while copying demo_seed")


def hydrate_partial_from_samples(settings: Settings) -> int:
    """Fill partial/failed docs from bundled sample QMS JSON (demo survival without LLM quota)."""
    if not settings.auto_seed_samples:
        return 0

    settings.ensure_dirs()
    hydrated = 0
    with Session(get_engine(settings)) as session:
        docs = session.exec(
            select(Document).where(Document.duplicate_of == None)  # noqa: E711
        ).all()
        for doc in docs:
            if doc.status == "extracted" and doc.extraction_status == "extracted":
                # Still refresh if extraction looks empty/partial in payload.
                row = session.exec(
                    select(ExtractionResult).where(ExtractionResult.document_id == doc.id)
                ).first()
                if row:
                    meta = (row.payload or {}).get("extraction_metadata") or {}
                    if meta.get("completion_status") == "complete" and not meta.get(
                        "extraction_errors"
                    ):
                        continue
            elif doc.status not in {
                "partial",
                "processed",
                "error",
                "uploaded",
                "queued",
                "processing",
            }:
                continue

            sample = _find_sample_json(doc.original_filename or doc.filename)
            if sample is None:
                logger.warning("hydrate skipped: no sample JSON for %s", doc.original_filename)
                continue
            try:
                payload = json.loads(sample.read_text(encoding="utf-8"))
                _persist_payload(session, doc, payload)
                hydrated += 1
                logger.info("hydrated %s from %s", doc.original_filename, sample.name)
            except Exception:
                logger.exception("hydrate failed for %s", doc.original_filename)
    return hydrated


# Back-compat name used by older main.py imports
async def seed_sample_policies_if_empty(settings: Settings) -> None:
    restore_demo_seed_if_needed(settings)
    hydrate_partial_from_samples(settings)
