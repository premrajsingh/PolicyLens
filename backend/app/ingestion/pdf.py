from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import Settings
from app.core.security import ensure_pdf_extension, is_ignored_path, safe_filename

logger = logging.getLogger(__name__)


@dataclass
class ParsedPage:
    page_number: int
    page_text: str
    tables: list[Any] = field(default_factory=list)
    parser: str = "text"
    ocr_used: bool = False


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def should_ocr(text: str, min_chars: int) -> bool:
    return len(text.strip()) < min_chars


def _ocr_page_image(pix_bytes: bytes, language: str) -> str:
    try:
        import io

        import pytesseract
        from PIL import Image

        image = Image.open(io.BytesIO(pix_bytes))
        return pytesseract.image_to_string(image, lang=language) or ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("ocr_failed error=%s", str(exc)[:200])
        return ""


def extract_tables_pdfplumber(path: Path, page_number: int) -> list[Any]:
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            if page_number < 1 or page_number > len(pdf.pages):
                return []
            page = pdf.pages[page_number - 1]
            tables = page.extract_tables() or []
            cleaned = []
            for table in tables:
                rows = [[(cell or "").strip() for cell in row] for row in table if row]
                if rows:
                    cleaned.append(rows)
            return cleaned
    except Exception as exc:  # noqa: BLE001
        logger.warning("pdfplumber_table_failed page=%s error=%s", page_number, str(exc)[:200])
        return []


def parse_pdf(path: Path, settings: Settings) -> list[ParsedPage]:
    ensure_pdf_extension(path.name)
    if is_ignored_path(path):
        raise ValueError("Ignored path")

    import pymupdf as fitz

    doc = fitz.open(path)
    if doc.needs_pass:
        doc.close()
        raise ValueError("Password-protected PDFs are not supported")
    if doc.page_count > settings.max_pdf_pages:
        doc.close()
        raise ValueError(f"PDF exceeds the {settings.max_pdf_pages}-page limit")
    pages: list[ParsedPage] = []
    try:
        for i in range(doc.page_count):
            page = doc[i]
            text = page.get_text("text", sort=True) or ""
            text = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines())
            parser = "text"
            ocr_used = False
            tables = extract_tables_pdfplumber(path, i + 1)
            if tables:
                # Keep table text as supplemental content
                table_text = "\n".join(
                    " | ".join(cell for cell in row if cell) for table in tables for row in table
                )
                if table_text.strip():
                    text = f"{text}\n\n[TABLE]\n{table_text}".strip()
                    if not (page.get_text("text") or "").strip():
                        parser = "table"

            if settings.ocr_enabled and should_ocr(text, settings.ocr_min_text_chars):
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                ocr_text = _ocr_page_image(pix.tobytes("png"), settings.ocr_language)
                if ocr_text.strip():
                    text = ocr_text
                    parser = "ocr"
                    ocr_used = True

            pages.append(
                ParsedPage(
                    page_number=i + 1,
                    page_text=text,
                    tables=tables,
                    parser=parser,
                    ocr_used=ocr_used,
                )
            )
    finally:
        doc.close()
    return pages


SECTION_HINTS: list[tuple[str, list[str]]] = [
    ("identity", ["insurer", "insurance company", "tpa", "policy number", "insured"]),
    ("previous_policy", ["policy period", "inception", "renewal", "premium", "tenure"]),
    ("policy_structure", ["family", "sum insured", "employee", "spouse", "children", "parents"]),
    ("demographics", ["lives covered", "employees", "dependents", "lives"]),
    (
        "room_hospitalization",
        ["room rent", "icu", "hospitalization", "pre-hospitalisation", "post-hospitalisation"],
    ),
    ("maternity", ["maternity", "delivery", "c-section", "caesarean", "new born", "vaccination"]),
    ("waiting_periods", ["waiting period", "pre-existing", "ped", "30 day", "first year"]),
    (
        "other_benefits",
        ["day care", "opd", "teleconsultation", "ayush", "organ donor", "bariatric"],
    ),
    ("infertility_ambulance", ["infertility", "surrogacy", "ambulance", "air ambulance"]),
    ("buffer_waivers", ["buffer", "corporate buffer", "waiver", "disease wise"]),
]


def detect_section(text: str) -> str:
    lower = text.lower()
    for section, keywords in SECTION_HINTS:
        if any(k in lower for k in keywords):
            return section
    return "general"


def chunk_pages(
    *,
    document_id: str,
    source_file: str,
    pages: list[ParsedPage],
    chunk_size: int = 1200,
    overlap: int = 150,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for page in pages:
        text = page.page_text or ""
        if not text.strip():
            continue
        start = 0
        idx = 0
        while start < len(text):
            end = min(len(text), start + chunk_size)
            piece = text[start:end].strip()
            if piece:
                chunk_id = f"{document_id}-page-{page.page_number}-chunk-{idx}"
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "document_id": document_id,
                        "source_file": source_file,
                        "page_number": page.page_number,
                        "section": detect_section(piece),
                        "text": piece,
                        "chunk_type": page.parser if page.parser != "ocr" else "ocr",
                        "parser": page.parser,
                        "text_hash": hashlib.sha256(piece.encode("utf-8")).hexdigest(),
                    }
                )
                idx += 1
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
    return chunks


def validate_upload_bytes(data: bytes, filename: str, max_bytes: int) -> str:
    if is_ignored_path(filename):
        raise ValueError("Ignored macOS metadata file")
    safe = safe_filename(filename)
    ensure_pdf_extension(safe)
    if len(data) > max_bytes:
        raise ValueError(f"File exceeds maximum size of {max_bytes} bytes")
    if len(data) < 5 or not data.startswith(b"%PDF"):
        raise ValueError("File does not look like a valid PDF")
    return safe
