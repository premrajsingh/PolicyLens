from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Column, Text
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: str = Field(default_factory=new_id, primary_key=True)
    filename: str
    original_filename: str
    content_hash: str = Field(index=True)
    file_size: int
    page_count: int = 0
    status: str = "uploaded"
    ocr_used: bool = False
    pinecone_status: str = "pending"
    neo4j_status: str = "pending"
    extraction_status: str = "pending"
    duplicate_of: str | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class DocumentPage(SQLModel, table=True):
    __tablename__ = "document_pages"

    id: str = Field(default_factory=new_id, primary_key=True)
    document_id: str = Field(index=True)
    page_number: int
    page_text: str = Field(default="", sa_column=Column(Text))
    tables_json: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    parser: str = "text"
    char_count: int = 0
    ocr_used: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class DocumentChunk(SQLModel, table=True):
    __tablename__ = "document_chunks"

    id: str = Field(default_factory=new_id, primary_key=True)
    chunk_id: str = Field(index=True, unique=True)
    document_id: str = Field(index=True)
    page_number: int
    section: str = "general"
    chunk_type: str = "text"
    parser: str = "text"
    text: str = Field(default="", sa_column=Column(Text))
    text_hash: str
    created_at: datetime = Field(default_factory=utcnow)


class ExtractionResult(SQLModel, table=True):
    __tablename__ = "extraction_results"

    id: str = Field(default_factory=new_id, primary_key=True)
    document_id: str = Field(index=True, unique=True)
    schema_version: str
    pipeline_version: str
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    overall_confidence: float = 0.0
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ProcessingJob(SQLModel, table=True):
    __tablename__ = "processing_jobs"

    id: str = Field(default_factory=new_id, primary_key=True)
    document_id: str = Field(index=True)
    job_type: str
    stage: str = "queued"
    status: str = "running"
    logs: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    error_message: str | None = None
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None


class ValidationResult(SQLModel, table=True):
    __tablename__ = "validation_results"

    id: str = Field(default_factory=new_id, primary_key=True)
    document_id: str = Field(index=True, unique=True)
    summary: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class AuditEvent(SQLModel, table=True):
    __tablename__ = "audit_events"

    id: str = Field(default_factory=new_id, primary_key=True)
    event_type: str
    document_id: str | None = Field(default=None, index=True)
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
