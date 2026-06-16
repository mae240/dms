"""Auth-DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel, normalize_email


class RegisterFirstAdminIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    full_name: str = Field(default="", max_length=200)

    # mode="before": strip/lower laeuft vor der EmailStr-Formatvalidierung.
    _norm = field_validator("email", mode="before")(normalize_email)


class LoginIn(BaseModel):
    # Bewusst nur normalisiert (kein EmailStr): ungueltige Eingaben sollen am
    # Login einheitlich als 401 enden, nicht als 422 (keine Format-Auskunft).
    email: str
    password: str = Field(min_length=1, max_length=256)

    _norm = field_validator("email")(normalize_email)


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
