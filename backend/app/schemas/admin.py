"""Admin-/Compliance-DTOs."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel


def _normalize_email(v: str) -> str:
    v = v.strip().lower()
    if "@" not in v or "." not in v.split("@")[-1]:
        raise ValueError("Ungueltige E-Mail-Adresse")
    return v


class AdminUserCreate(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=256)
    full_name: str = Field(default="", max_length=200)
    is_superadmin: bool = False

    _norm = field_validator("email")(_normalize_email)


class RetentionSetIn(BaseModel):
    retention_until: date | None = None


class LegalHoldSetIn(BaseModel):
    legal_hold: bool


class AdminUserOut(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_superadmin: bool
    is_anonymized: bool
    created_at: datetime


class AuditLogOut(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    project_id: uuid.UUID | None
    ip_address: str | None
    metadata: dict[str, Any] | None = Field(default=None)
    created_at: datetime


class ExportOut(ORMModel):
    id: uuid.UUID
    subject_user_id: uuid.UUID
    requested_by: uuid.UUID
    status: str
    expires_at: datetime | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None
