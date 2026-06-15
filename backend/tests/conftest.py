"""Test-Fixtures.

Verwendet eine SEPARATE Postgres-Test-DB (kein SQLite — JSONB/CHECK/Trigger
verhalten sich dort anders). Jeder Test laeuft in einer Transaktion, die am
Ende zurueckgerollt wird (Isolation). Session-Commits im App-Code landen via
join_transaction_mode='create_savepoint' nur in einem Savepoint.
"""

from __future__ import annotations

from collections.abc import Generator
from urllib.parse import urlsplit, urlunsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel

import dms_core.models  # noqa: F401  (registriert alle Tabellen)
from app.main import app
from dms_core.config import settings
from dms_core.db import get_session

_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION dms_block_audit_mutation() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' OR TG_OP = 'TRUNCATE' THEN
        RAISE EXCEPTION 'audit_logs ist append-only: % ist nicht erlaubt', TG_OP;
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.actor_user_id IS DISTINCT FROM OLD.actor_user_id
       OR NEW.action IS DISTINCT FROM OLD.action
       OR NEW.entity_type IS DISTINCT FROM OLD.entity_type
       OR NEW.entity_id IS DISTINCT FROM OLD.entity_id
       OR NEW.project_id IS DISTINCT FROM OLD.project_id
       OR NEW.metadata IS DISTINCT FROM OLD.metadata
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'audit_logs ist append-only: nur IP-Schwaerzung erlaubt';
    END IF;
    IF NEW.ip_address IS NOT NULL THEN
        RAISE EXCEPTION 'audit_logs: ip_address darf nur auf NULL gesetzt werden';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_audit_logs_no_mutation ON audit_logs;
CREATE TRIGGER trg_audit_logs_no_mutation
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION dms_block_audit_mutation();
DROP TRIGGER IF EXISTS trg_audit_logs_no_truncate ON audit_logs;
CREATE TRIGGER trg_audit_logs_no_truncate
BEFORE TRUNCATE ON audit_logs
FOR EACH STATEMENT EXECUTE FUNCTION dms_block_audit_mutation();
"""


def _test_db_url() -> str:
    parts = urlsplit(settings.database_url)
    return urlunsplit(parts._replace(path="/dms_test"))


def _admin_url() -> str:
    parts = urlsplit(settings.database_url)
    return urlunsplit(parts._replace(path="/postgres"))


@pytest.fixture(scope="session")
def engine() -> Generator[Engine, None, None]:
    admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'dms_test'")
        ).first()
        if not exists:
            conn.execute(text("CREATE DATABASE dms_test"))
    admin.dispose()

    eng = create_engine(_test_db_url())
    # Extension wie in der Migration bereitstellen: create_all() erzeugt den
    # GIN-Index ix_documents_title_trgm (gin_trgm_ops), der pg_trgm voraussetzt.
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    SQLModel.metadata.drop_all(eng)
    SQLModel.metadata.create_all(eng)
    with eng.begin() as conn:
        conn.execute(text(_TRIGGER_SQL))
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Generator[Session, None, None]:
    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


@pytest.fixture
def tmp_storage(tmp_path):  # noqa: ANN001, ANN201
    from dms_core.storage.local import LocalFilesystemBackend

    return LocalFilesystemBackend(tmp_path / "storage")


@pytest.fixture
def tmp_export_storage(tmp_path):  # noqa: ANN001, ANN201
    from dms_core.storage.local import LocalFilesystemBackend

    return LocalFilesystemBackend(tmp_path / "exports")


@pytest.fixture(autouse=True)
def _no_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verhindert echtes Celery-Enqueue an Redis waehrend der Tests."""
    monkeypatch.setattr("app.api.routes_documents.enqueue_process_version", lambda *_a, **_k: None)
    monkeypatch.setattr("app.api.routes_admin.enqueue_export_user_data", lambda *_a, **_k: None)


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> None:
    """Verhindert Rate-Limit-Flakiness zwischen Tests (Redis ist nicht im Rollback)."""
    try:
        import redis

        r = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        for key in r.scan_iter("rl:*"):
            r.delete(key)
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override_session() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_session] = _override_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
