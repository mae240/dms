"""Projekt- und Mitgliedschafts-Modelle.

Ein Projekt = Kundenengagement oder interner Bereich. Zugriff ist strikt
projektgebunden (Privacy by Default, Art. 25): die Mitgliedschaft in
project_members entscheidet ueber Sichtbarkeit und Rolle.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from dms_core.enums import ProjectRole, ProjectStatus, enum_check
from dms_core.models._helpers import (
    created_at_field,
    fk_uuid,
    pk_field,
    updated_at_field,
)


class Project(SQLModel, table=True):
    __tablename__ = "projects"
    __table_args__ = (CheckConstraint(f"status {enum_check(ProjectStatus)}", name="status_valid"),)

    id: uuid.UUID = pk_field()
    name: str = Field(sa_column=Column(String(200), nullable=False))
    description: str | None = Field(default=None, sa_column=Column(String(2000), nullable=True))
    owner_id: uuid.UUID = fk_uuid("users.id", nullable=False, ondelete="RESTRICT")
    status: str = Field(
        default=ProjectStatus.active,
        sa_column=Column(String(20), nullable=False, index=True, server_default="active"),
    )
    created_at: datetime = created_at_field()
    updated_at: datetime = updated_at_field()
    deleted_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class ProjectMember(SQLModel, table=True):
    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="project_user"),
        CheckConstraint(f"role {enum_check(ProjectRole)}", name="role_valid"),
    )

    id: uuid.UUID = pk_field()
    project_id: uuid.UUID = fk_uuid("projects.id", nullable=False, ondelete="CASCADE")
    user_id: uuid.UUID = fk_uuid("users.id", nullable=False, ondelete="CASCADE", index=True)
    role: str = Field(sa_column=Column(String(20), nullable=False))
    created_at: datetime = created_at_field()


class RetentionRule(SQLModel, table=True):
    """Maximal-Aufbewahrung pro Projekt (+ optional Kategorie). Art. 5(1e).

    category = NULL  -> Projekt-Default (gilt fuer alle Kategorien ohne eigene Regel)
    max_days = NULL  -> exempt (nie automatisch loeschen)
    Aufloesung: spezifischste Regel (Projekt+Kategorie) schlaegt Projekt-Default.
    """

    __tablename__ = "retention_rules"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category",
            name="retention_rule_scope",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: uuid.UUID = pk_field()
    project_id: uuid.UUID = fk_uuid("projects.id", nullable=False, ondelete="CASCADE", index=True)
    category: str | None = Field(default=None, sa_column=Column(String(100), nullable=True))
    max_days: int | None = Field(default=None, sa_column=Column(Integer(), nullable=True))
    created_at: datetime = created_at_field()
