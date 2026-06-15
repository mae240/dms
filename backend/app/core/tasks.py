"""Duenne Bruecke zum Enqueuen von Celery-Tasks (per Name, ohne Worker-Import).

Wird IMMER erst NACH dem DB-Commit aufgerufen, damit der Worker die Zeile
findet (Race vermeiden). Enqueue ist best-effort: faellt das Broker-Enqueue
aus, bleibt die Version im Status 'uploaded' und kann re-enqueued werden.
"""

from __future__ import annotations

import uuid

from dms_core.celery_app import (
    TASK_EXPORT_USER_DATA,
    TASK_PROCESS_VERSION,
    celery_app,
)


def enqueue_process_version(version_id: uuid.UUID) -> None:
    try:
        celery_app.send_task(TASK_PROCESS_VERSION, args=[str(version_id)])
    except Exception:  # noqa: BLE001  (Broker-Ausfall darf den Request nicht killen)
        pass


def enqueue_export_user_data(export_id: uuid.UUID) -> None:
    try:
        celery_app.send_task(TASK_EXPORT_USER_DATA, args=[str(export_id)])
    except Exception:  # noqa: BLE001
        pass
