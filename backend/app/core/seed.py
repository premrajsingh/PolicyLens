from __future__ import annotations

import logging
import shutil
from pathlib import Path

from app.config import Settings

logger = logging.getLogger(__name__)


def demo_seed_dirs() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[3]
    return [
        Path("/app/demo_seed"),
        repo_root / "data" / "demo_seed",
    ]


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


# Back-compat name used by older main.py imports
async def seed_sample_policies_if_empty(settings: Settings) -> None:
    restore_demo_seed_if_needed(settings)
