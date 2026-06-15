"""Einstiegspunkt fuer den Celery-Worker.

Importiert die geteilte celery_app und registriert alle Task-Module, indem es
sie importiert. `celery -A worker.celery_tasks.celery_app` findet so alle Tasks.
"""

from __future__ import annotations

from dms_core.celery_app import celery_app

# Task-Module importieren -> registriert die @celery_app.task-Funktionen.
from worker.tasks import maintenance, processing  # noqa: F401,E402

__all__ = ["celery_app"]
