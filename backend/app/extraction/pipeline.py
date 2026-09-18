from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlmodel import Session, select

from app.config import Settings
from app.core.jobs import document_lock
from app.core.version import PIPELINE_VERSION, SCHEMA_VERSION
from app.db.models import (
    AuditEvent,
    Document,
    DocumentChunk,
    DocumentPage,
    ExtractionResult,
    ProcessingJob,
    ValidationResult,
    utcnow,
)
from app.extraction.fields import FIELD_GROUPS, GROUP_ATTR, mine_field_from_evidence
from app.extraction.normalize import normalize_field
from app.extraction.semantics import apply_schema_rules
from app.ingestion.pdf import chunk_pages, parse_pdf, sha256_bytes, validate_upload_bytes
from app.models.schema import (
    DocumentInfo,
    EvidenceItem,
    ExtractedPolicy,
    ExtractionMetadata,
    FieldValue,
    unknown_field,
)
from app.providers.embeddings.provider import EmbeddingProvider, create_embedding_provider
from app.providers.graph_store.factory import create_graph_store
from app.providers.llm.provider import create_llm_provider
from app.providers.vector_store.base import Chunk
from app.providers.vector_store.factory import create_vector_store
from app.retrieval.hybrid import BOOSTED_TOP_K_GROUPS, FIELD_GROUP_QUERIES, hybrid_search
from app.validation.engine import validate_and_score

logger = logging.getLogger(__name__)

STAGES = [
    "parsing",
    "ocr",
    "chunking",
    "embedding",
    "pinecone_indexing",
    "retrieval",
    "structured_extraction",
    "validation",
    "neo4j_sync",
    "complete",
]


class PipelineService:
    def __init__(self, settings: Settings, session: Session) -> None:
        self.settings = settings
        self.session = session
        self.embedder: EmbeddingProvider = create_embedding_provider(settings)
        self.vector_store = create_vector_store(settings)
        self.graph_store = create_graph_store(settings)
        self.llm = create_llm_provider(settings)

    def _log(self, job: ProcessingJob, message: str) -> None:
        logs = list(job.logs or [])
        logs.append(f"{datetime.now(UTC).isoformat()} {message}")
        job.logs = logs
        self.session.add(job)
        self.session.commit()

    def _set_stage(self, job: ProcessingJob, document: Document, stage: str) -> None:
        job.stage = stage
        # Do not pollute document.status with mid-pipeline stage names
        # (e.g. structured_extraction) — those made the UI look broken.
        if stage in {"uploaded", "processed", "extracted", "error", "duplicate"}:
            document.status = stage
        elif stage == "complete":
            pass
        else:
            document.status = "processing"
        document.updated_at = utcnow()
        self.session.add(job)
        self.session.add(document)
        self.session.commit()
        self._log(job, f"stage={stage}")

    def save_upload(self, data: bytes, filename: str) -> Document:
        safe = validate_upload_bytes(data, filename, self.settings.max_upload_bytes)
        content_hash = sha256_bytes(data)
        existing = self.session.exec(
            select(Document).where(
                Document.content_hash == content_hash,
                Document.duplicate_of == None,  # noqa: E711
            )
        ).first()
        if existing is None:
            existing = self.session.exec(
                select(Document).where(Document.content_hash == content_hash)
            ).first()
        dest = self.settings.documents_dir / f"{content_hash}.pdf"
        dest.write_bytes(data)
        if existing and existing.status != "duplicate":
            dup = Document(
                filename=safe,
                original_filename=filename,
                content_hash=content_hash,
                file_size=len(data),
                status="duplicate",
                duplicate_of=existing.id,
            )
            self.session.add(dup)
            self.session.add(
                AuditEvent(
                    event_type="document_duplicate",
                    document_id=dup.id,
                    details={"duplicate_of": existing.id, "filename": safe},
                )
            )
            self.session.commit()
            self.session.refresh(dup)
            return dup
        if existing and existing.status == "duplicate" and existing.duplicate_of:
            # Point new duplicate at the original
            dup = Document(
                filename=safe,
                original_filename=filename,
                content_hash=content_hash,
                file_size=len(data),
                status="duplicate",
                duplicate_of=existing.duplicate_of,
            )
            self.session.add(dup)
            self.session.commit()
            self.session.refresh(dup)
            return dup

        doc = Document(
            filename=safe,
            original_filename=filename,
            content_hash=content_hash,
            file_size=len(data),
            status="uploaded",
        )
        self.session.add(doc)
        self.session.add(
            AuditEvent(
                event_type="document_uploaded", document_id=doc.id, details={"filename": safe}
            )
        )
        self.session.commit()
        self.session.refresh(doc)
        return doc

    async def process_document(self, document_id: str, *, reprocess: bool = False) -> ProcessingJob:
        with document_lock(document_id):
            return await self._process_document(document_id, reprocess=reprocess)

    async def _process_document(
        self, document_id: str, *, reprocess: bool = False
    ) -> ProcessingJob:
        document = self.session.get(Document, document_id)
        if not document:
            raise ValueError("Document not found")
        if document.status == "duplicate":
            raise ValueError("Duplicate document; process the original instead")

        job = ProcessingJob(
            document_id=document_id, job_type="reprocess" if reprocess else "process"
        )
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)

        try:
            path = self.settings.documents_dir / f"{document.content_hash}.pdf"
            self._set_stage(job, document, "parsing")
            pages = parse_pdf(path, self.settings)
            if not pages or not any(p.page_text.strip() for p in pages):
                raise ValueError("No readable text found. Enable OCR for scanned PDFs.")
            # Reprocessing invalidates old extractions and validation, never display stale answers.
            for model in (ExtractionResult, ValidationResult):
                for old in self.session.exec(
                    select(model).where(model.document_id == document_id)
                ).all():
                    self.session.delete(old)
            document.extraction_status = "pending"
            document.error_message = None
            document.neo4j_status = "pending"
            await self.graph_store.delete_policy(document_id)
            ocr_used = any(p.ocr_used for p in pages)
            document.ocr_used = ocr_used
            document.page_count = len(pages)
            self._set_stage(job, document, "ocr" if ocr_used else "chunking")

            # Replace pages/chunks
            for row in self.session.exec(
                select(DocumentPage).where(DocumentPage.document_id == document_id)
            ).all():
                self.session.delete(row)
            for row in self.session.exec(
                select(DocumentChunk).where(DocumentChunk.document_id == document_id)
            ).all():
                self.session.delete(row)
            self.session.execute(
                text("DELETE FROM chunk_fts WHERE document_id = :document_id"),
                {"document_id": document_id},
            )
            self.session.commit()

            for page in pages:
                self.session.add(
                    DocumentPage(
                        document_id=document_id,
                        page_number=page.page_number,
                        page_text=page.page_text,
                        tables_json=page.tables,
                        parser=page.parser,
                        char_count=len(page.page_text or ""),
                        ocr_used=page.ocr_used,
                    )
                )
            self.session.commit()

            self._set_stage(job, document, "chunking")
            chunk_dicts = chunk_pages(
                document_id=document_id, source_file=document.filename, pages=pages
            )
            for c in chunk_dicts:
                self.session.add(
                    DocumentChunk(
                        chunk_id=c["chunk_id"],
                        document_id=document_id,
                        page_number=c["page_number"],
                        section=c["section"],
                        chunk_type=c["chunk_type"],
                        parser=c["parser"],
                        text=c["text"],
                        text_hash=c["text_hash"],
                    )
                )
                self.session.execute(
                    text(
                        """
                        INSERT INTO chunk_fts(chunk_id, document_id, section, page_number, text)
                        VALUES (:chunk_id, :document_id, :section, :page_number, :text)
                        """
                    ),
                    {
                        "chunk_id": c["chunk_id"],
                        "document_id": document_id,
                        "section": c["section"],
                        "page_number": str(c["page_number"]),
                        "text": c["text"],
                    },
                )
            self.session.commit()

            self._set_stage(job, document, "embedding")
            embeddings = (
                self.embedder.embed([c["text"] for c in chunk_dicts]) if chunk_dicts else []
            )
            chunks: list[Chunk] = []
            for c, emb in zip(chunk_dicts, embeddings, strict=True):
                chunks.append(
                    Chunk(
                        chunk_id=c["chunk_id"],
                        document_id=document_id,
                        source_file=document.filename,
                        page_number=c["page_number"],
                        section=c["section"],
                        text=c["text"],
                        chunk_type=c["chunk_type"],
                        parser=c["parser"],
                        text_hash=c["text_hash"],
                        embedding=emb,
                    )
                )

            self._set_stage(job, document, "pinecone_indexing")
            try:
                await self.vector_store.delete_document(document_id)
                await self.vector_store.upsert_chunks(chunks)
                # Only mark "indexed" when vectors landed in Pinecone — local store
                # must not fake a Pinecone success (that skipped later re-upserts).
                if self.settings.vector_store == "pinecone":
                    document.pinecone_status = "indexed"
                    self._log(job, f"pinecone_upserted_chunks={len(chunks)}")
                else:
                    document.pinecone_status = "local_indexed"
                    self._log(job, f"local_vector_upserted_chunks={len(chunks)}")
            except Exception as exc:  # noqa: BLE001
                document.pinecone_status = "error"
                self._log(job, f"vector_index_error={exc}")
                raise

            self._set_stage(job, document, "complete")
            document.status = "processed"
            document.updated_at = utcnow()
            job.status = "completed"
            job.finished_at = utcnow()
            self.session.add(document)
            self.session.add(job)
            self.session.commit()
            return job
        except Exception as exc:  # noqa: BLE001
            logger.exception("process_failed document_id=%s", document_id)
            self.session.rollback()
            job.status = "failed"
            job.error_message = f"Processing failed ({type(exc).__name__}). Check server logs."
            job.finished_at = utcnow()
            document.status = "error"
            document.error_message = job.error_message
            self.session.add(job)
            self.session.add(document)
            self.session.commit()
            raise

    async def extract_policy(self, document_id: str) -> ExtractedPolicy:
        with document_lock(document_id):
            try:
                return await self._extract_policy(document_id)
            except Exception as exc:
                logger.exception("extract_failed document_id=%s", document_id)
                self.session.rollback()
                document = self.session.get(Document, document_id)
                if document:
                    document.status = "error"
                    document.extraction_status = "error"
                    document.error_message = (
                        f"Extraction failed ({type(exc).__name__}). "
                        "Retry or check provider settings."
                    )
                    self.session.add(document)
                    for job in self.session.exec(
                        select(ProcessingJob).where(
                            ProcessingJob.document_id == document_id,
                            ProcessingJob.status == "running",
                        )
                    ).all():
                        job.status = "failed"
                        job.error_message = document.error_message
                        job.finished_at = utcnow()
                        self.session.add(job)
                    self.session.commit()
                raise

    async def _extract_policy(self, document_id: str) -> ExtractedPolicy:
        document = self.session.get(Document, document_id)
        if not document:
            raise ValueError("Document not found")
        if document.status == "duplicate":
            raise ValueError("Duplicate document; extract the original instead")
        if document.status in {"uploaded", "error"} or not document.page_count:
            await self._process_document(document_id)
        document.error_message = None

        job = ProcessingJob(document_id=document_id, job_type="extract")
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        started = datetime.now(UTC)

        pages = self.session.exec(
            select(DocumentPage).where(DocumentPage.document_id == document_id)
        ).all()
        pages.sort(key=lambda page: page.page_number)
        page_texts = {p.page_number: p.page_text for p in pages}
        full_context = [
            {
                "page_number": p.page_number,
                "text": p.page_text,
                "section": "document",
                "parser": p.parser,
                "source_file": document.filename,
            }
            for p in pages
        ]
        classification = None
        for p in pages:
            match = re.search(
                r"(?:GROUP PERSONAL ACCIDENT POLICY|GROUP (?:MEDICAL|HEALTH)(?: INSURANCE)?"
                r"|Policy Certificate - Group Care[^\n]*|Policy Document [–-] Health Plus)",
                p.page_text,
                re.I,
            )
            if match:
                classification = FieldValue(
                    value="gpa" if "personal accident" in match[0].lower() else "gmc",
                    status="covered",
                    confidence=1,
                    evidence=[
                        EvidenceItem(
                            source_file=document.filename, page_number=p.page_number, quote=match[0]
                        )
                    ],
                )
                break
        parsers = sorted({p.parser for p in pages})

        self._set_stage(job, document, "retrieval")
        policy = ExtractedPolicy(
            schema_version=SCHEMA_VERSION,
            pipeline_version=PIPELINE_VERSION,
            document=DocumentInfo(
                document_id=document.id,
                filename=document.filename,
                content_hash=document.content_hash,
                page_count=document.page_count,
                ocr_used=document.ocr_used,
                parsers=parsers,
            ),
            extraction_metadata=ExtractionMetadata(
                provider=self.llm.name,
                model=getattr(self.llm, "model", None),
                generated_at=started.isoformat(),
                pinecone_indexing_status=document.pinecone_status,
                neo4j_sync_status=document.neo4j_status,
                ocr_used=document.ocr_used,
                parsers_used=parsers,
                retrieval_method="full_document"
                if sum(len(p.page_text) for p in pages) <= 36000
                else "hybrid",
            ),
        )

        self._set_stage(job, document, "structured_extraction")
        for group, fields in FIELD_GROUPS.items():
            if (
                classification
                and classification.value == "gpa"
                and group not in {"identity", "current_policy", "previous_policy"}
            ):
                group_obj = getattr(policy, GROUP_ATTR[group])
                for field_name in fields:
                    setattr(
                        group_obj,
                        field_name,
                        FieldValue(
                            status="not_applicable",
                            conditions=[
                                "The source is a Group Personal Accident policy, "
                                "outside GMC extraction scope."
                            ],
                            evidence=classification.evidence,
                            confidence=1,
                        ),
                    )
                continue
            query = FIELD_GROUP_QUERIES.get(group, group)
            top_k = self.settings.top_k
            if group in BOOSTED_TOP_K_GROUPS:
                top_k = max(top_k, 14)
            # Small certificates fit whole: do not lose clauses to top-k retrieval.
            # Long policies use hybrid retrieval plus per-field lexical evidence diversity.
            if sum(len(p.page_text) for p in pages) <= 36000:
                evidence_chunks = full_context
            else:
                retrieved = await hybrid_search(
                    self.session,
                    self.vector_store,
                    self.embedder,
                    query=query,
                    document_id=document_id,
                    top_k=top_k,
                    source_file=document.filename,
                )
                from app.retrieval.hybrid import lexical_search

                unique = {c.chunk_id: c for c in retrieved}
                for field_name in fields:
                    for c in lexical_search(
                        self.session,
                        query=field_name.replace("_", " "),
                        document_id=document_id,
                        top_k=2,
                    ):
                        unique.setdefault(c.chunk_id, c)
                evidence_chunks = [
                    {
                        "chunk_id": c.chunk_id,
                        "page_number": c.page_number,
                        "section": c.section,
                        "text": c.text,
                        "parser": c.parser,
                        "source_file": document.filename,
                        "score": c.score,
                    }
                    for c in list(unique.values())[:24]
                ]
            llm_payload: dict[str, Any] = {}
            try:
                llm_payload = await self.llm.extract_group(
                    group=group,
                    fields=fields,
                    evidence_chunks=evidence_chunks,
                    source_file=document.filename,
                )
            except Exception as exc:
                self._log(job, f"llm_error group={group} type={type(exc).__name__}")
                policy.extraction_metadata.extraction_errors.append(
                    f"{group}: provider request failed ({type(exc).__name__})"
                )

            for field_name in fields:
                raw = llm_payload.get(field_name) if isinstance(llm_payload, dict) else None
                try:
                    fv = FieldValue.model_validate(raw) if raw else unknown_field()
                except Exception:  # noqa: BLE001
                    fv = unknown_field()
                    fv.warnings.append("invalid_llm_field_payload")
                    policy.extraction_metadata.extraction_errors.append(
                        f"{group}.{field_name}: invalid provider response"
                    )

                # Deterministic miner supplements mock/empty LLM without inventing values
                if fv.value is None:
                    mined = mine_field_from_evidence(field_name, evidence_chunks, group=group)
                    if mined.value is not None:
                        fv = mined

                if group == "identity" and field_name == "policy_type" and classification:
                    fv = classification
                fv = normalize_field(field_name, fv)

                attr = GROUP_ATTR.get(group)
                if attr is None:
                    if field_name in FIELD_GROUPS["identity"]:
                        setattr(policy, field_name, fv)
                else:
                    group_obj = getattr(policy, attr)
                    setattr(group_obj, field_name, fv)

        if self.llm.name == "mock":
            policy.extraction_metadata.completion_status = "offline"
        elif policy.extraction_metadata.extraction_errors:
            policy.extraction_metadata.completion_status = "partial"
        policy = apply_schema_rules(policy, page_texts)
        self._set_stage(job, document, "validation")
        policy = validate_and_score(policy, page_texts=page_texts, source_file=document.filename)
        duration = (datetime.now(UTC) - started).total_seconds()
        policy.extraction_metadata.processing_duration_seconds = duration

        self._set_stage(job, document, "neo4j_sync")
        try:
            await self.graph_store.upsert_policy(policy)
            document.neo4j_status = (
                "synced" if self.settings.graph_store == "neo4j" else "local_synced"
            )
            policy.extraction_metadata.neo4j_sync_status = document.neo4j_status
        except Exception as exc:  # noqa: BLE001
            document.neo4j_status = "error"
            policy.extraction_metadata.neo4j_sync_status = "error"
            self._log(job, f"graph_sync_error={exc}")
            policy.validation.extraction_warnings.append(
                "Graph sync failed; authoritative JSON remains available."
            )

        existing = self.session.exec(
            select(ExtractionResult).where(ExtractionResult.document_id == document_id)
        ).first()
        payload = policy.model_dump(mode="json")
        if existing:
            existing.payload = payload
            existing.overall_confidence = policy.validation.overall_confidence
            existing.updated_at = utcnow()
            self.session.add(existing)
        else:
            self.session.add(
                ExtractionResult(
                    document_id=document_id,
                    schema_version=SCHEMA_VERSION,
                    pipeline_version=PIPELINE_VERSION,
                    payload=payload,
                    overall_confidence=policy.validation.overall_confidence,
                )
            )
        vr = self.session.exec(
            select(ValidationResult).where(ValidationResult.document_id == document_id)
        ).first()
        summary = policy.validation.model_dump()
        if vr:
            vr.summary = summary
            self.session.add(vr)
        else:
            self.session.add(ValidationResult(document_id=document_id, summary=summary))

        document.extraction_status = (
            "partial" if policy.extraction_metadata.completion_status == "partial" else "extracted"
        )
        document.status = document.extraction_status
        document.updated_at = utcnow()
        job.status = "completed"
        job.stage = "complete"
        job.finished_at = utcnow()
        self.session.add(document)
        self.session.add(job)
        self.session.commit()
        return policy

    def write_output(self, policy: ExtractedPolicy, output_dir: Path | None = None) -> Path:
        out = output_dir or (self.settings.output_dir / "sample")
        out.mkdir(parents=True, exist_ok=True)
        safe = re_sub_filename(policy.document.filename)
        path = out / f"{safe}.json"
        path.write_text(json.dumps(policy.model_dump(mode="json"), indent=2), encoding="utf-8")
        return path


def re_sub_filename(name: str) -> str:
    import re

    base = Path(name).stem
    return re.sub(r"[^A-Za-z0-9._\-]+", "_", base)[:120]
