"""Projekt-DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel
from dms_core.enums import ProjectRole


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: str | None = Field(default=None, pattern="^(active|archived)$")


class ProjectOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None
    owner_id: uuid.UUID
    status: str
    created_at: datetime
    my_role: str | None = None  # Rolle des anfragenden Users in diesem Projekt


class MemberAddIn(BaseModel):
    email: str
    role: ProjectRole = ProjectRole.viewer

    @field_validator("email")
    @classmethod
    def _norm(cls, v: str) -> str:
        return v.strip().lower()


class MemberRoleUpdate(BaseModel):
    role: ProjectRole


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str
    created_at: datetime


class ProjectDetailOut(ProjectOut):
    members: list[MemberOut] = []
