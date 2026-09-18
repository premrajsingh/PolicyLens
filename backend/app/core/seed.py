from __future__ import annotations

import logging
from pathlib import Path

from sqlmodel import Session, select

from app.config import Settings
from app.db.models import Document
from app.db.session import get_engine
from app.extraction.pipeline import PipelineService
from app.core.security import is_ignored_path

logger = logging.getLogger(__name__)


def sample_policy_dirs() -> list[Path]:
    """Candidate locations for bundled assignment PDFs (Docker + local repo)."""
    repo_root = Path(__file__).resolve().parents[3]
    return [
        Path("/app/sample_policies"),
        repo_root / "data" / "sample_policies",
    ]


async def seed_sample_policies_if_empty(settings: Settings) -> None:
    """When the DB is empty, ingest + extract bundled sample PDFs for the public demo."""
    if not settings.auto_seed_samples:
        return

    sample_dir = next((p for p in sample_policy_dirs() if p.is_dir()), None)
    if sample_dir is None:
        logger.warning("auto_seed skipped: sample_policies directory not found")
        return

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
                await pipeline.process_document(doc.id, reprocess=True)
                await pipeline.extract_policy(doc.id)
                logger.info("auto_seed complete %s id=%s", path.name, doc.id)
        except Exception:
            logger.exception("auto_seed failed for %s", path.name)
