"""Dokument- und Versions-DTOs."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class DocumentMetadataPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    category: str | None = Field(default=None, max_length=100)
    # Lifecycle nur active <-> archived; Loeschung laeuft ueber DELETE.
    status: str | None = Field(default=None, pattern="^(active|archived)$")


class VersionOut(ORMModel):
    id: uuid.UUID
    version_number: int
    file_name: str
    file_hash: str
    mime_type: str
    size_bytes: int
    processing_status: str
    processing_error: str | None
    created_at: datetime
    processed_at: datetime | None


class DocumentListItem(BaseModel):
    id: uuid.UUID
    title: str
    category: str | None
    status: str
    latest_version_number: int | None
    latest_processing_status: str | None
    version_count: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    purge_after: datetime | None = None
    legal_hold: bool = False
    retention_until: date | None = None


class RecentDocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    project_id: uuid.UUID
    project_name: str
    status: str
    latest_processing_status: str | None
    updated_at: datetime


class DocumentDetailOut(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None
    category: str | None
    status: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    retention_until: date | None
    legal_hold: bool
    purge_after: datetime | None
    current_version: VersionOut | None = None
