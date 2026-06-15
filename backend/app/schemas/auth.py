"""Auth-DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel


def _normalize_email(v: str) -> str:
    v = v.strip().lower()
    if "@" not in v or "." not in v.split("@")[-1]:
        raise ValueError("Ungueltige E-Mail-Adresse")
    return v


class RegisterFirstAdminIn(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=256)
    full_name: str = Field(default="", max_length=200)

    _norm = field_validator("email")(_normalize_email)


class LoginIn(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=256)

    _norm = field_validator("email")(_normalize_email)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # Sekunden bis Ablauf des Access-Tokens


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_superadmin: bool
    created_at: datetime
