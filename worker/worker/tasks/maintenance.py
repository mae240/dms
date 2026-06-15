"""Wartungs-/Compliance-Tasks (Beat-gesteuert).

Duenne Wrapper um die testbare Kernlogik in dms_core.maintenance: hier nur
session_scope + Storage-Aufloesung. Lange Jobs sind durch PURGE_BATCH gechunked
und idempotent (vgl. Celery visibility_timeout in dms_core.celery_app).
"""

from __future__ import annotations

from dms_core import maintenance
from dms_core.celery_app import (
    TASK_AUTO_EXPIRE,
    TASK_CLEANUP_AUDIT_IP,
    TASK_CLEANUP_EXPORTS,
    TASK_EXPORT_USER_DATA,
    TASK_PURGE_DOCUMENTS,
    TASK_REWRAP_BLOBS,
    celery_app,
)
from dms_core.config import settings
from dms_core.db import session_scope
from dms_core.storage import get_export_storage, get_storage


@celery_app.task(name=TASK_PURGE_DOCUMENTS)
def purge_deleted_documents() -> int:
    with session_scope() as session:
        return maintenance.purge_deleted_documents(session, get_storage())


@celery_app.task(name=TASK_EXPORT_USER_DATA)
def export_user_data(export_id: str) -> str:
    import uuid

    with session_scope() as session:
        return maintenance.produce_export(session, uuid.UUID(export_id), get_export_storage())


@celery_app.task(name=TASK_CLEANUP_EXPORTS)
def cleanup_expired_exports() -> int:
    with session_scope() as session:
        return maintenance.cleanup_expired_exports(session, get_export_storage())


@celery_app.task(name=TASK_CLEANUP_AUDIT_IP)
def cleanup_audit_ip() -> int:
    with session_scope() as session:
        return maintenance.cleanup_audit_ip(session, settings.audit_ip_retention_days)


@celery_app.task(name=TASK_AUTO_EXPIRE)
def auto_soft_delete_expired() -> int:
    with session_scope() as session:
        return maintenance.auto_soft_delete_expired(session)


@celery_app.task(name=TASK_REWRAP_BLOBS)
def rewrap_blobs() -> dict:
    with session_scope() as session:
        return maintenance.rewrap_blobs(session, get_storage())
