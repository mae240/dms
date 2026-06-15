"""Health-/Readiness-Endpunkt."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from dms_core.db import engine

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness + DB-Erreichbarkeit."""
    db_ok = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = "error"
    return {"status": "ok", "database": db_ok}
