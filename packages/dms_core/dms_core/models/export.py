"""User-Datenexport (Art. 15/20 Auskunft/Datenuebertragbarkeit).

Eine Export-Datei ist geballte PII: kurzlebig (expires_at), abgesichert
(Download nur fuer Berechtigte) und nach Ablauf via cleanup_expired_exports
geloescht (Datenminimierung).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, String, Text
from sqlmodel import Field, SQLModel

from dms_core.enums import ExportStatus, enum_check
from dms_core.models._helpers import created_at_field, fk_uuid, pk_field


class UserExport(SQLModel, table=True):
    __tablename__ = "user_exports"
    __table_args__ = (
        CheckConstraint(f"status {enum_check(ExportStatus)}", name="status_valid"),
    )

    id: uuid.UUID = pk_field()
    # Person, deren Daten exportiert werden:
    subject_user_id: uuid.UUID = fk_uuid(
        "users.id", nullable=False, ondelete="CASCADE", index=True
    )
    # Admin, der den Export ausgeloest hat:
    requested_by: uuid.UUID = fk_uuid("users.id", nullable=False, ondelete="RESTRICT")
    status: str = Field(
        default=ExportStatus.pending,
        sa_column=Column(String(20), nullable=False, server_default="pending"),
    )
    storage_key: str | None = Field(default=None, sa_column=Column(String(512), nullable=True))
    expires_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True, index=True)
    )
    error: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    created_at: datetime = created_at_field()
    completed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
