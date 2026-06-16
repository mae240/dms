"""Gemeinsame Schema-Bausteine (DTOs)."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlmodel import Session, select
from sqlmodel.sql.expression import SelectOfScalar

T = TypeVar("T")


class ORMModel(BaseModel):
    """Basis fuer Response-DTOs, die aus ORM-Objekten gefuellt werden."""

    model_config = ConfigDict(from_attributes=True)


def normalize_email(v: str) -> str:
    v = v.strip().lower()
    if "@" not in v or "." not in v.split("@")[-1]:
        raise ValueError("Ungueltige E-Mail-Adresse")
    return v


class Page(BaseModel, Generic[T]):
    """Einheitliche, paginierte Antwort fuer Listen-Endpunkte."""

    items: list[T]
    total: int
    limit: int
    offset: int


def paginate(
    session: Session, stmt: SelectOfScalar, *, limit: int, offset: int
) -> tuple[list[Any], int]:
    """Generischer Pagination-Helfer fuer einfache list_*-Queries.

    Zaehlt die Gesamtzahl ueber die uebergebene (noch nicht limitierte) Query
    und liefert die Seite (limit/offset). `stmt` muss eine Selektion ohne
    eigene order_by/limit/offset-Klausel auf Count-Ebene sein; die Reihenfolge
    fuer die Page wird vom Aufrufer per .order_by am stmt gesetzt.
    """
    total = session.exec(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).one()
    rows = session.exec(stmt.limit(limit).offset(offset)).all()
    return list(rows), total
