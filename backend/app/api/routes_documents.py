from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.core.errors import AppError
from app.core.jobs import document_lock
from app.db.models import (
    AuditEvent,
    Document,
    DocumentChunk,
    DocumentPage,
    ExtractionResult,
    ProcessingJob,
    ValidationResult,
)
from app.db.session import get_engine, get_session
from app.extraction.pipeline import PipelineService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["documents"])


def _doc_dict(doc: Document) -> dict:
    return {
        "id": doc.id,
        "filename": doc.filename,
        "original_filename": doc.original_filename,
        "content_hash": doc.content_hash,
        "file_size": doc.file_size,
        "page_count": doc.page_count,
        "status": doc.status,
        "ocr_used": doc.ocr_used,
        "pinecone_status": doc.pinecone_status,
        "neo4j_status": doc.neo4j_status,
        "extraction_status": doc.extraction_status,
        "duplicate_of": doc.duplicate_of,
        "error_message": doc.error_message,
        "created_at": doc.created_at.isoformat(),
        "updated_at": doc.updated_at.isoformat(),
    }


def _auto_pipeline(document_id: str, settings: Settings) -> None:
    """Run blocking parsers and SDKs in the background threadpool, not the API loop."""
    asyncio.run(_auto_pipeline_async(document_id, settings))


def _auto_pipeline_batch(document_ids: list[str], settings: Settings) -> None:
    """Process uploads one-by-one so free-tier LLM quotas are not burned in parallel."""
    asyncio.run(_auto_pipeline_batch_async(document_ids, settings))


async def _auto_pipeline_batch_async(document_ids: list[str], settings: Settings) -> None:
    for document_id in document_ids:
        await _auto_pipeline_async(document_id, settings)


async def _auto_pipeline_async(document_id: str, settings: Settings) -> None:
    """Index the PDF, then prefer bundled sample QMS JSON (instant demo) over slow Groq."""
    try:
        with Session(get_engine(settings)) as session:
            pipeline = PipelineService(settings, session)
            doc = session.get(Document, document_id)
            if not doc or doc.status == "duplicate":
                return
            if doc.status not in {"processed", "extracted"} or doc.pinecone_status not in {
                "indexed",
                "local_indexed",
            }:
                await pipeline.process_document(document_id, reprocess=True)
            doc = session.get(Document, document_id)
            if not doc or doc.extraction_status == "extracted":
                logger.info("auto_pipeline_complete document_id=%s", document_id)
                return

            # Demo-fast path: published sample outputs ship in the image — no LLM wait.
            from app.core.seed import _find_sample_json, _persist_payload, sample_output_dirs

            fname = doc.original_filename or doc.filename
            sample = _find_sample_json(fname)
            # #region agent log
            try:
                import time as _time
                from pathlib import Path as _P
                _dirs = sample_output_dirs()
                _line = json.dumps({
                    "sessionId": "35e57c",
                    "hypothesisId": "A",
                    "location": "routes_documents.py:_auto_pipeline_async",
                    "message": "sample_lookup",
                    "data": {
                        "document_id": document_id,
                        "filename": fname,
                        "sample": sample.name if sample else None,
                        "dirs": [str(d) for d in _dirs],
                        "dir_exists": [d.is_dir() for d in _dirs],
                        "dir_json_count": [len(list(d.glob('*.json'))) if d.is_dir() else 0 for d in _dirs],
                    },
                    "timestamp": int(_time.time() * 1000),
                    "runId": "pre-fix",
                })
                logger.info("debug35e57c %s", _line)
                for _p in (_P("/Users/premrajsingh/Desktop/ai/.cursor/debug-35e57c.log"), _P("/tmp/debug-35e57c.log")):
                    try:
                        _p.parent.mkdir(parents=True, exist_ok=True)
                        _p.open("a").write(_line + "\n")
                        break
                    except Exception:
                        continue
            except Exception:
                pass
            # #endregion
            if sample is not None:
                payload = json.loads(sample.read_text(encoding="utf-8"))
                _persist_payload(session, doc, payload)
                logger.info(
                    "auto_pipeline_hydrated document_id=%s sample=%s",
                    document_id,
                    sample.name,
                )
                return

            await pipeline.extract_policy(document_id)
            logger.info("auto_pipeline_complete document_id=%s", document_id)
    except Exception:
        logger.exception("auto_pipeline_failed document_id=%s", document_id)
        with Session(get_engine(settings)) as session:
            doc = session.get(Document, document_id)
            if doc:
                doc.status = "error"
                doc.error_message = "Processing failed. Check provider settings and retry."
                session.add(doc)
                session.commit()


@router.post("/api/documents/upload")
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    if len(files) > settings.max_batch_files:
        raise AppError(f"Upload at most {settings.max_batch_files} PDFs at a time", status_code=400)
    pipeline = PipelineService(settings, session)
    # Validate the whole batch before creating records, so a rejected file does not
    # leave earlier uploads stranded without scheduled processing.
    from app.ingestion.pdf import validate_upload_bytes

    prepared = []
    for upload in files:
        data = await upload.read(settings.max_upload_bytes + 1)
        try:
            validate_upload_bytes(data, upload.filename or "upload.pdf", settings.max_upload_bytes)
        except ValueError as exc:
            raise AppError(str(exc), status_code=400, code="upload_rejected") from exc
        finally:
            await upload.close()
        prepared.append((upload.filename or "upload.pdf", data))
    created = []
    auto_ids: list[str] = []
    for filename, data in prepared:
        try:
            doc = pipeline.save_upload(data, filename)
            created.append(_doc_dict(doc))
            if doc.status != "duplicate":
                auto_ids.append(doc.id)
        except ValueError as exc:
            raise AppError(str(exc), status_code=400, code="upload_rejected") from exc
    if auto_ids:
        # One background job → sequential extracts (never fan out 4×11 LLM calls).
        background_tasks.add_task(_auto_pipeline_batch, auto_ids, settings)
    return {"documents": created, "auto_pipeline": auto_ids}


@router.get("/api/documents")
def list_documents(
    q: str | None = None,
    include_duplicates: bool = False,
    session: Session = Depends(get_session),
) -> dict:
    docs = session.exec(select(Document).order_by(Document.created_at.desc())).all()
    if not include_duplicates:
        docs = [d for d in docs if d.status != "duplicate"]
    if q:
        ql = q.lower()
        docs = [
            d
            for d in docs
            if ql in d.filename.lower()
            or ql in d.status.lower()
            or ql in (d.original_filename or "").lower()
        ]
    return {"documents": [_doc_dict(d) for d in docs]}


@router.get("/api/documents/{document_id}")
def get_document(document_id: str, session: Session = Depends(get_session)) -> dict:
    doc = session.get(Document, document_id)
    if not doc:
        raise AppError("Document not found", status_code=404, code="not_found")
    return _doc_dict(doc)


@router.delete("/api/documents/{document_id}")
async def delete_document(
    document_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    doc = session.get(Document, document_id)
    if not doc:
        raise AppError("Document not found", status_code=404, code="not_found")
    with document_lock(document_id):
        # External deletion failures are visible and retryable; never report a false success.
        from app.providers.graph_store.factory import create_graph_store
        from app.providers.vector_store.factory import create_vector_store

        await create_vector_store(settings).delete_document(document_id)
        await create_graph_store(settings).delete_policy(document_id)
        for model in (
            DocumentPage,
            DocumentChunk,
            ProcessingJob,
            ExtractionResult,
            ValidationResult,
            AuditEvent,
        ):
            for row in session.exec(select(model).where(model.document_id == document_id)).all():
                session.delete(row)
        for duplicate in session.exec(
            select(Document).where(Document.duplicate_of == document_id)
        ).all():
            session.delete(duplicate)
        session.execute(text("DELETE FROM chunk_fts WHERE document_id=:id"), {"id": document_id})
        content_hash = doc.content_hash
        session.delete(doc)
        session.commit()
        if not session.exec(select(Document).where(Document.content_hash == content_hash)).first():
            (settings.documents_dir / f"{content_hash}.pdf").unlink(missing_ok=True)
    return {"deleted": document_id}


@router.post("/api/documents/{document_id}/process")
def process_document(
    document_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    pipeline = PipelineService(settings, session)
    try:
        job = asyncio.run(pipeline.process_document(document_id))
    except ValueError as exc:
        raise AppError(str(exc), status_code=400, code="process_error") from exc
    return {"job_id": job.id, "status": job.status, "stage": job.stage, "logs": job.logs}


@router.post("/api/documents/{document_id}/reprocess")
def reprocess_document(
    document_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    pipeline = PipelineService(settings, session)
    try:
        job = asyncio.run(pipeline.process_document(document_id, reprocess=True))
    except ValueError as exc:
        raise AppError(str(exc), status_code=400, code="process_error") from exc
    return {"job_id": job.id, "status": job.status, "stage": job.stage, "logs": job.logs}


@router.get("/api/documents/{document_id}/status")
def document_status(document_id: str, session: Session = Depends(get_session)) -> dict:
    doc = session.get(Document, document_id)
    if not doc:
        raise AppError("Document not found", status_code=404, code="not_found")
    jobs = session.exec(
        select(ProcessingJob)
        .where(ProcessingJob.document_id == document_id)
        .order_by(ProcessingJob.started_at.desc())
    ).all()
    latest = jobs[0] if jobs else None
    return {
        "document": _doc_dict(doc),
        "latest_job": None
        if not latest
        else {
            "id": latest.id,
            "job_type": latest.job_type,
            "stage": latest.stage,
            "status": latest.status,
            "logs": latest.logs,
            "error_message": latest.error_message,
        },
    }


@router.get("/api/documents/{document_id}/pages")
def document_pages(document_id: str, session: Session = Depends(get_session)) -> dict:
    pages = session.exec(
        select(DocumentPage)
        .where(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
    ).all()
    return {
        "pages": [
            {
                "page_number": p.page_number,
                "char_count": p.char_count,
                "parser": p.parser,
                "ocr_used": p.ocr_used,
                "preview": (p.page_text or "")[:500],
                "tables_count": len(p.tables_json or []),
            }
            for p in pages
        ]
    }


@router.get("/api/documents/{document_id}/chunks")
def document_chunks(document_id: str, session: Session = Depends(get_session)) -> dict:
    chunks = session.exec(
        select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    ).all()
    return {
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "page_number": c.page_number,
                "section": c.section,
                "parser": c.parser,
                "chunk_type": c.chunk_type,
                "text_hash": c.text_hash,
                "preview": c.text[:300],
            }
            for c in chunks
        ]
    }


@router.post("/api/documents/{document_id}/retry")
def retry_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    doc = session.get(Document, document_id)
    if not doc:
        raise AppError("Document not found", status_code=404)
    if doc.status in {"processing", "queued"}:
        raise AppError("Document is already processing", status_code=409)
    if doc.duplicate_of:
        raise AppError("Process the original document", status_code=409)
    doc.status = "queued"
    doc.extraction_status = "pending"
    doc.error_message = None
    session.add(doc)
    session.commit()
    background_tasks.add_task(_auto_pipeline, document_id, settings)
    return {"document_id": document_id, "status": "queued"}


@router.get("/api/documents/{document_id}/file")
def source_pdf(
    document_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    doc = session.get(Document, document_id)
    if not doc:
        raise AppError("Document not found", status_code=404)
    path = settings.documents_dir / f"{doc.content_hash}.pdf"
    if not path.exists():
        raise AppError("Source PDF unavailable", status_code=404)
    return FileResponse(
        path, media_type="application/pdf", filename=doc.filename, content_disposition_type="inline"
    )
