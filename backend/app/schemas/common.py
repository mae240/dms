"""Gemeinsame Schema-Bausteine (DTOs)."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    """Basis fuer Response-DTOs, die aus ORM-Objekten gefuellt werden."""

    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    """Einheitliche, paginierte Antwort fuer Listen-Endpunkte."""

    items: list[T]
    total: int
    limit: int
    offset: int
