"""Geteilte Celery-App (Broker = Redis).

Hardening gegen die typischen Fallen:
- task_acks_late + reject_on_worker_lost + prefetch=1  -> robuste Zustellung
- task_ignore_result=True  -> kanonischer Job-Status lebt in PostgreSQL
  (document_versions.processing_status), Redis bleibt reiner Broker
- broker_transport_options.visibility_timeout > laengster Task  -> verhindert,
  dass Redis lange Wartungsjobs (purge/export) erneut zustellt und sie DOPPELT
  laufen (Doppel-Purge-Risiko!). Lange Jobs zusaetzlich chunked/batched halten.

Task-Namen werden hier zentral referenziert, damit das Backend Tasks per Name
enqueuen kann (send_task), ohne den Worker-Code importieren zu muessen.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from dms_core.config import settings

# Kanonische Task-Namen (vom Worker registriert, vom Backend per Name enqueued)
TASK_PROCESS_VERSION = "tasks.process_document_version"
TASK_PURGE_DOCUMENTS = "tasks.purge_deleted_documents"
TASK_EXPORT_USER_DATA = "tasks.export_user_data"
TASK_CLEANUP_EXPORTS = "tasks.cleanup_expired_exports"
TASK_CLEANUP_AUDIT_IP = "tasks.cleanup_audit_ip"
TASK_AUTO_EXPIRE = "tasks.auto_soft_delete_expired"

celery_app = Celery("dms", broker=settings.celery_broker_url)

celery_app.conf.update(
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    broker_transport_options={"visibility_timeout": settings.celery_visibility_timeout},
    broker_connection_retry_on_startup=True,
    task_default_queue="processing",
    task_routes={
        TASK_PROCESS_VERSION: {"queue": "processing"},
        TASK_PURGE_DOCUMENTS: {"queue": "maintenance"},
        TASK_EXPORT_USER_DATA: {"queue": "maintenance"},
        TASK_CLEANUP_EXPORTS: {"queue": "maintenance"},
        TASK_CLEANUP_AUDIT_IP: {"queue": "maintenance"},
        TASK_AUTO_EXPIRE: {"queue": "maintenance"},
    },
    beat_schedule={
        "purge-deleted-documents": {
            "task": TASK_PURGE_DOCUMENTS,
            "schedule": crontab(minute=0, hour=3),  # taeglich 03:00 UTC
        },
        "cleanup-expired-exports": {
            "task": TASK_CLEANUP_EXPORTS,
            "schedule": crontab(minute=30),  # stuendlich
        },
        "cleanup-audit-ip": {
            "task": TASK_CLEANUP_AUDIT_IP,
            "schedule": crontab(minute=15, hour=4),  # taeglich 04:15 UTC
        },
        "auto-expire-documents": {
            "task": TASK_AUTO_EXPIRE,
            "schedule": crontab(minute=30, hour=2),  # taeglich 02:30 UTC, vor dem Purge
        },
    },
)
