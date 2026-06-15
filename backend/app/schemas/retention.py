"""DTOs fuer Retention-Regeln (Maximal-Aufbewahrung pro Projekt/Kategorie)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class RetentionRuleIn(BaseModel):
    category: str | None = Field(default=None, max_length=100)
    max_days: int | None = Field(default=None, ge=1, le=36500)  # None = exempt (nie loeschen)


class RetentionRuleDelete(BaseModel):
    category: str | None = Field(default=None, max_length=100)


class RetentionRuleOut(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    category: str | None
    max_days: int | None
    created_at: datetime
