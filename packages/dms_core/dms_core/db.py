"""Synchrone DB-Engine, Session-Factory und Naming-Convention.

Bewusst sync (kein async): SQLModel ist sync-ausgelegt, Celery-Worker sind
sync, FastAPI fuehrt sync-Endpunkte automatisch im Threadpool aus. Eine
einzige Engine/Session-Factory wird von Backend (Depends) und Worker
(session_scope) geteilt.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager

from sqlalchemy import MetaData
from sqlmodel import Session, SQLModel, create_engine

from dms_core.config import settings

# Einheitliche Constraint-Namen — MUSS vor der ersten Tabellen-/Constraint-
# Erzeugung gesetzt sein (deshalb importieren die Models dieses Modul zuerst).
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# SQLModel teilt sich eine globale MetaData; Convention darauf anwenden.
metadata: MetaData = SQLModel.metadata
metadata.naming_convention = NAMING_CONVENTION  # type: ignore[assignment]

# Pool auf die FastAPI-Threadpool-Groesse (40) abstimmen, sonst droht
# Pool-Erschoepfung (Default 5+10 < 40 gleichzeitige Sync-Endpunkte).
engine = create_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_pre_ping=True,
    echo=False,
)


def get_session() -> Generator[Session, None, None]:
    """FastAPI-Dependency: eine Session pro Request, sauber geschlossen."""
    with Session(engine) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """Worker-Kontext: eigene Session pro Task, commit/rollback automatisch."""
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
