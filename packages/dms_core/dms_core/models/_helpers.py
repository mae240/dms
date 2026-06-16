"""Spalten-Helper, damit die Modelle DRY und konsistent bleiben.

Wichtig: sa_column-Objekte gehoeren je genau EINER Tabelle. Deshalb geben die
Helper bei jedem Aufruf eine FRISCHE Column/Field-Instanz zurueck.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Column, DateTime, ForeignKey, Uuid, func
from sqlmodel import Field


def pk_field() -> Any:
    """UUIDv4 Primary Key (server-/client-seitig generiert, nicht erratbar)."""
    return Field(sa_column=Column(Uuid(), primary_key=True, default=uuid.uuid4, nullable=False))


def fk_uuid(
    target: str,
    *,
    nullable: bool,
    ondelete: str,
    index: bool = False,
) -> Any:
    """Fremdschluessel auf eine UUID-Spalte mit explizitem ON DELETE."""
    return Field(
        sa_column=Column(
            Uuid(),
            ForeignKey(target, ondelete=ondelete),
            nullable=nullable,
            index=index,
        )
    )


def created_at_field(*, index: bool = False) -> Any:
    return Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
            index=index,
        )
    )


def updated_at_field() -> Any:
    return Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        )
    )
