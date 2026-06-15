"""Verzeichnis von Verarbeitungstaetigkeiten (Art. 30 VVT).

Schlanke Tabelle mit statischem Seed; kein dynamisches UI im MVP. Ein DMS
verarbeitet per Definition fremde personenbezogene Dokumente -> VVT-Relevanz.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from dms_core.models._helpers import created_at_field, pk_field, updated_at_field


class ProcessingActivity(SQLModel, table=True):
    __tablename__ = "processing_activities"

    id: uuid.UUID = pk_field()
    name: str = Field(sa_column=Column(String(200), nullable=False))
    purpose: str = Field(sa_column=Column(Text(), nullable=False))
    legal_basis: str = Field(sa_column=Column(String(200), nullable=False))
    data_categories: list[Any] = Field(
        default_factory=list, sa_column=Column(JSONB, nullable=False)
    )
    retention_policy: str = Field(sa_column=Column(Text(), nullable=False))
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()
