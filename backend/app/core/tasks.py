"""Duenne Bruecke zum Enqueuen von Celery-Tasks (per Name, ohne Worker-Import).

Wird IMMER erst NACH dem DB-Commit aufgerufen, damit der Worker die Zeile
findet (Race vermeiden). Enqueue ist best-effort: faellt das Broker-Enqueue
aus, bleibt die Version im Status 'uploaded' und kann re-enqueued werden.
"""

from __future__ import annotations

import logging
import uuid

from dms_core.celery_app import (
    TASK_EXPORT_USER_DATA,
    TASK_PROCESS_VERSION,
    celery_app,
)

logger = logging.getLogger(__name__)


def _enqueue(task_name: str, entity_id: uuid.UUID) -> None:
    # Broker-Ausfall darf den Request nicht killen (best-effort, re-enqueue moeglich) —
    # aber geloggt, sonst bleibt ein haengender 'uploaded'-Status unsichtbar.
    try:
        celery_app.send_task(task_name, args=[str(entity_id)])
    except Exception:
        logger.exception("Enqueue von %s fehlgeschlagen (id=%s)", task_name, entity_id)


def enqueue_process_version(version_id: uuid.UUID) -> None:
    _enqueue(TASK_PROCESS_VERSION, version_id)


def enqueue_export_user_data(export_id: uuid.UUID) -> None:
    _enqueue(TASK_EXPORT_USER_DATA, export_id)
