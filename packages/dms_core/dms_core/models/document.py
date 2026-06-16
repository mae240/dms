"""Dokument- und Versions-Modelle.

Trennung:
- Document.status      = Lifecycle (nutzergesteuert: active/archived/deleted)
- DocumentVersion.processing_status = technischer Pipeline-Zustand der Datei

Lösch-/Retention-Logik (zentrales Compliance-Detail):
- retention_until = fachliche/rechtliche Mindest-Aufbewahrung
- deleted_at      = Zeitpunkt des Soft-Delete
- purge_after     = technische Grace-Period bis Hard-Delete (deleted_at + PURGE_GRACE_DAYS)
- legal_hold      = blockiert JEDEN Purge bedingungslos
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel

from dms_core.enums import DocumentStatus, ProcessingStatus, enum_check
from dms_core.models._helpers import (
    created_at_field,
    fk_uuid,
    pk_field,
    updated_at_field,
)


class Document(SQLModel, table=True):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(f"status {enum_check(DocumentStatus)}", name="status_valid"),
        # Trigram-GIN-Index fuer ILIKE '%term%' Titelsuche (leading wildcard,
        # B-Tree nicht nutzbar). Benoetigt Extension pg_trgm (siehe Migration).
        Index(
            "ix_documents_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )

    id: uuid.UUID = pk_field()
    project_id: uuid.UUID = fk_uuid("projects.id", nullable=False, ondelete="CASCADE", index=True)
    title: str = Field(sa_column=Column(String(300), nullable=False))
    description: str | None = Field(default=None, sa_column=Column(String(4000), nullable=True))
    category: str | None = Field(default=None, sa_column=Column(String(100), nullable=True))
    status: str = Field(
        default=DocumentStatus.active,
        sa_column=Column(String(20), nullable=False, index=True, server_default="active"),
    )
    created_by: uuid.UUID = fk_uuid("users.id", nullable=False, ondelete="RESTRICT")
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()

    # Soft-Delete / Compliance
    deleted_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    deleted_by: uuid.UUID | None = fk_uuid("users.id", nullable=True, ondelete="SET NULL")
    retention_until: date | None = Field(default=None, sa_column=Column(Date(), nullable=True))
    legal_hold: bool = Field(default=False, nullable=False)
    purge_after: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class DocumentVersion(SQLModel, table=True):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="document_version"),
        CheckConstraint(
            f"processing_status {enum_check(ProcessingStatus)}", name="processing_status_valid"
        ),
    )

    id: uuid.UUID = pk_field()
    document_id: uuid.UUID = fk_uuid("documents.id", nullable=False, ondelete="CASCADE", index=True)
    version_number: int = Field(nullable=False)
    # Originaler Dateiname (nur fuer Anzeige/Download-Disposition):
    file_name: str = Field(sa_column=Column(String(400), nullable=False))
    file_hash: str = Field(sa_column=Column(String(64), nullable=False))  # sha256 hex
    # Opaker, relativer Key — NIE ein oeffentlicher Pfad/URL:
    storage_key: str = Field(sa_column=Column(String(512), nullable=False))
    mime_type: str = Field(sa_column=Column(String(255), nullable=False))
    size_bytes: int = Field(sa_column=Column(BigInteger(), nullable=False))
    processing_status: str = Field(
        default=ProcessingStatus.uploaded,
        sa_column=Column(String(20), nullable=False, index=True, server_default="uploaded"),
    )
    processing_error: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    extracted_text: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    preview_storage_key: str | None = Field(
        default=None, sa_column=Column(String(512), nullable=True)
    )
    created_by: uuid.UUID = fk_uuid("users.id", nullable=False, ondelete="RESTRICT")
    created_at: datetime = created_at_field()
    processed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
