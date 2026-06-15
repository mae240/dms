"""Task: process_document_version.

Pipeline pro Version: SHA-256-Reverify (Integritaet), MIME-Recheck (Defense in
Depth), Textextraktion. Setzt processing_status auf ready / failed (technischer
Fehler) / quarantined (Sicherheitsverdacht). Idempotent: bereits 'ready'-
Versionen werden uebersprungen (acks_late kann redeliveren).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from dms_core.celery_app import TASK_PROCESS_VERSION, celery_app
from dms_core.config import settings
from dms_core.db import session_scope
from dms_core.enums import ProcessingStatus
from dms_core.files import HEAD_BYTES, guess_mime_from_bytes
from dms_core.models.document import DocumentVersion
from dms_core.storage import get_storage
from worker.extract import extract_text


def evaluate_blob(
    data: bytes, *, expected_hash: str, stored_mime: str
) -> tuple[ProcessingStatus, str | None, str | None]:
    """Reine Pipeline-Logik (ohne DB/Storage) — gut testbar.

    Liefert (Status, Fehlertext, extrahierter Text):
    - SHA-256-Mismatch -> failed (Integritaet)
    - MIME nicht erlaubt / weicht ab -> quarantined (Sicherheitsverdacht)
    - sonst -> ready (+ extrahierter Text)
    """
    actual_hash = hashlib.sha256(data).hexdigest()
    actual_mime = guess_mime_from_bytes(data[:HEAD_BYTES])

    if actual_hash != expected_hash:
        return ProcessingStatus.failed, "Integritaetsfehler: SHA-256 stimmt nicht ueberein", None
    if actual_mime not in settings.allowed_mime_set or actual_mime != stored_mime:
        return (
            ProcessingStatus.quarantined,
            f"MIME-Mismatch: erkannt={actual_mime}, gespeichert={stored_mime}",
            None,
        )
    return ProcessingStatus.ready, None, extract_text(actual_mime, data)


@celery_app.task(name=TASK_PROCESS_VERSION, bind=True)
def process_document_version(self, version_id: str) -> str:  # noqa: ANN001
    vid = uuid.UUID(version_id)

    # 1) Beanspruchen / als 'processing' markieren (idempotent).
    with session_scope() as session:
        version = session.get(DocumentVersion, vid)
        if version is None:
            return "missing"
        if version.processing_status == ProcessingStatus.ready:
            return "already_ready"
        version.processing_status = ProcessingStatus.processing
        version.processing_error = None
        session.add(version)
        storage_key = version.storage_key
        expected_hash = version.file_hash
        stored_mime = version.mime_type

    # 2) Verifizieren + extrahieren (ausserhalb der Transaktion).
    try:
        data = b"".join(get_storage().open_stream(storage_key))
        new_status, error, text = evaluate_blob(
            data, expected_hash=expected_hash, stored_mime=stored_mime
        )
    except Exception as exc:  # noqa: BLE001
        new_status = ProcessingStatus.failed
        error = f"Verarbeitung fehlgeschlagen: {exc}"[:1000]
        text = None

    # 3) Ergebnis persistieren.
    with session_scope() as session:
        version = session.get(DocumentVersion, vid)
        if version is None:
            return "missing"
        version.processing_status = new_status
        version.processing_error = error
        version.extracted_text = text
        version.processed_at = datetime.now(UTC)
        session.add(version)

    return new_status.value
