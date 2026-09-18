#!/usr/bin/env python3
"""Print filled vs unknown FieldValue counts for each extracted document."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlmodel import Session, select

from app.config import get_settings
from app.db.models import Document, ExtractionResult
from app.db.session import get_engine, init_db


def _count_fields(payload: object) -> tuple[int, int]:
    filled = 0
    unknown = 0

    def walk(o: object) -> None:
        nonlocal filled, unknown
        if isinstance(o, dict):
            if "evidence" in o and "status" in o:
                if o.get("value") is not None:
                    filled += 1
                else:
                    unknown += 1
                return
            for v in o.values():
                walk(v)

    walk(payload)
    return filled, unknown


def main() -> int:
    get_settings.cache_clear()
    settings = get_settings()
    init_db(settings)
    with Session(get_engine(settings)) as session:
        for doc in session.exec(select(Document)).all():
            if doc.status == "duplicate":
                continue
            row = session.exec(
                select(ExtractionResult).where(ExtractionResult.document_id == doc.id)
            ).first()
            filled, unknown = _count_fields(row.payload) if row else (0, 0)
            print(
                f"{doc.filename[:45]:45} ext={doc.extraction_status:10} "
                f"filled={filled:3} unknown={unknown:3} has_json={bool(row)}"
            )
            if "GHI" in doc.filename and row:
                payload = row.payload
                print("  insurer", (payload.get("insurer") or {}).get("value"))
                print("  conf", (payload.get("validation") or {}).get("overall_confidence"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
