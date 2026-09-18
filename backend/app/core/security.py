from __future__ import annotations

import re
from pathlib import Path

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._\-\s()]+")


def safe_filename(name: str) -> str:
    base = Path(name).name
    if base.startswith("._") or "__MACOSX" in Path(name).parts:
        raise ValueError("Unsafe or ignored filename")
    cleaned = _SAFE_NAME.sub("_", base).strip().strip(".")
    if not cleaned or cleaned.startswith("._"):
        raise ValueError("Unsafe or ignored filename")
    if "__MACOSX" in cleaned:
        raise ValueError("Ignored macOS metadata path")
    return cleaned[:200]


def is_ignored_path(path: str | Path) -> bool:
    p = Path(path)
    parts = set(p.parts)
    if "__MACOSX" in parts:
        return True
    if p.name.startswith("._"):
        return True
    return False


def ensure_pdf_extension(filename: str) -> None:
    if not filename.lower().endswith(".pdf"):
        raise ValueError("Only PDF files are supported")
