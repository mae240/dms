"""User- und RefreshToken-Modelle."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, String
from sqlmodel import Field, SQLModel

from dms_core.models._helpers import (
    created_at_field,
    fk_uuid,
    pk_field,
    updated_at_field,
)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: uuid.UUID = pk_field()
    email: str = Field(sa_column=Column(String(320), unique=True, index=True, nullable=False))
    hashed_password: str = Field(nullable=False)
    # PII-Felder — bei Art.-17-Loeschung anonymisierbar:
    full_name: str = Field(default="", nullable=False)
    is_active: bool = Field(default=True, nullable=False)
    is_superadmin: bool = Field(default=False, nullable=False)
    is_anonymized: bool = Field(default=False, nullable=False)
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()


class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_tokens"

    id: uuid.UUID = pk_field()
    user_id: uuid.UUID = fk_uuid("users.id", nullable=False, ondelete="CASCADE", index=True)
    # NUR der Hash wird gespeichert, nie der Klartext-Token:
    token_hash: str = Field(sa_column=Column(String(128), unique=True, nullable=False))
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True)
    )
    revoked_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    user_agent: str | None = Field(default=None, sa_column=Column(String(256), nullable=True))
    ip_address: str | None = Field(default=None, sa_column=Column(String(45), nullable=True))
    created_at: datetime = created_at_field()
