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

from sqlalchemy import Column, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from dms_core.models._helpers import created_at_field, fk_uuid, pk_field


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: uuid.UUID = pk_field()
    actor_user_id: uuid.UUID | None = fk_uuid("users.id", nullable=True, ondelete="SET NULL")
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
