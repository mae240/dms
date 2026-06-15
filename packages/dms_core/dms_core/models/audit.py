"""Audit-Log (Art. 5(2) Rechenschaftspflicht).

Append-only: keine UPDATE/DELETE-Endpoints. Zusaetzlich erzwingt ein
DB-Trigger (siehe Migration) die Unveraenderlichkeit auf Datenbankebene.
actor_user_id ist ON DELETE SET NULL — der Log bleibt auch nach
Anonymisierung/Loeschung eines Users erhalten.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, Index, String, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from dms_core.models._helpers import created_at_field, fk_uuid, pk_field


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"
    __table_args__ = (
        # Hot-Path: Audit-Liste je Projekt, neueste zuerst (Filter + Sortierung).
        Index("ix_audit_logs_project_created", "project_id", text("created_at DESC")),
    )

    id: uuid.UUID = pk_field()
    # index=True -> ix_audit_logs_actor_user_id (Art-15-Export: WHERE actor_user_id = ?)
    actor_user_id: uuid.UUID | None = fk_uuid(
        "users.id", nullable=True, ondelete="SET NULL", index=True
    )
    action: str = Field(sa_column=Column(String(64), nullable=False, index=True))
    entity_type: str = Field(sa_column=Column(String(64), nullable=False))
    entity_id: uuid.UUID | None = Field(default=None, sa_column=Column(Uuid(), nullable=True))
    project_id: uuid.UUID | None = fk_uuid(
        "projects.id", nullable=True, ondelete="SET NULL", index=True
    )
    ip_address: str | None = Field(default=None, sa_column=Column(String(45), nullable=True))
    # 'metadata' ist bei SQLAlchemy reserviert -> Python-Attribut metadata_,
    # DB-Spalte heisst 'metadata'.
    metadata_: dict[str, Any] | None = Field(
        default=None, sa_column=Column("metadata", JSONB, nullable=True)
    )
    created_at: datetime = created_at_field(index=True)
