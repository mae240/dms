"""Task: process_document_version.

Pipeline pro Version: SHA-256-Reverify (Integritaet), MIME-Recheck (Defense in
Depth), Textextraktion. Setzt processing_status auf ready / failed (technischer
Fehler) / quarantined (Sicherheitsverdacht). Idempotent: bereits 'ready'-
Versionen werden uebersprungen (acks_late kann redeliveren).
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
import uuid
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime

from dms_core.celery_app import TASK_PROCESS_VERSION, celery_app
from dms_core.config import settings
from dms_core.db import session_scope
from dms_core.enums import ProcessingStatus
from dms_core.files import HEAD_BYTES, guess_mime_from_bytes
from dms_core.models.document import DocumentVersion
from dms_core.storage import get_storage
from worker.extract import extract_text_from_file

logger = logging.getLogger(__name__)

# Bis hierhin wird im RAM gepuffert, darueber spillt das Tempfile auf Disk.
# So liegt nie die ganze (bis 50 MB) Datei gleichzeitig als bytes im Heap.
_SPOOL_MAX_BYTES = 4 * 1024 * 1024


def evaluate_stream(
    chunks: Iterable[bytes], *, expected_hash: str, stored_mime: str
) -> tuple[ProcessingStatus, str | None, str | None]:
    """Reine Pipeline-Logik (ohne DB/Storage) — streamend, gut testbar.

    Liest den Stream EINMAL in ein SpooledTemporaryFile und berechnet dabei
    gleichzeitig den SHA-256-Digest sowie die ersten HEAD_BYTES (fuer MIME).
    So wird die Datei nie komplett als bytes-Objekt im RAM gehalten.

    Liefert (Status, Fehlertext, extrahierter Text):
    - SHA-256-Mismatch -> failed (Integritaet)
    - MIME nicht erlaubt / weicht ab -> quarantined (Sicherheitsverdacht)
    - sonst -> ready (+ extrahierter Text)
    """
    digest = hashlib.sha256()
    head = bytearray()
    with tempfile.SpooledTemporaryFile(max_size=_SPOOL_MAX_BYTES, mode="w+b") as spool:
        for chunk in chunks:
            digest.update(chunk)
            if len(head) < HEAD_BYTES:
                head.extend(chunk[: HEAD_BYTES - len(head)])
            spool.write(chunk)

        actual_hash = digest.hexdigest()
        actual_mime = guess_mime_from_bytes(bytes(head))

        if actual_hash != expected_hash:
            return (
                ProcessingStatus.failed,
                "Integritaetsfehler: SHA-256 stimmt nicht ueberein",
                None,
            )
        if actual_mime not in settings.allowed_mime_set or actual_mime != stored_mime:
            return (
                ProcessingStatus.quarantined,
                f"MIME-Mismatch: erkannt={actual_mime}, gespeichert={stored_mime}",
                None,
            )

        spool.seek(0)
        text = extract_text_from_file(actual_mime, spool)
    return ProcessingStatus.ready, None, text


def evaluate_blob(
    data: bytes, *, expected_hash: str, stored_mime: str
) -> tuple[ProcessingStatus, str | None, str | None]:
    """bytes-Komfort-Wrapper um `evaluate_stream` (kleine/Test-Inhalte)."""
    return evaluate_stream(iter((data,)), expected_hash=expected_hash, stored_mime=stored_mime)


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

    # 2) Verifizieren + extrahieren (ausserhalb der Transaktion, streamend).
    try:
        stream: Iterator[bytes] = get_storage().open_stream(storage_key)
        # Die Extraktion validiert die Lesbarkeit; der Text wird bewusst
        # verworfen (nicht persistiert) — siehe Datenminimierung unten.
        new_status, error, _text = evaluate_stream(
            stream, expected_hash=expected_hash, stored_mime=stored_mime
        )
    except Exception:  # noqa: BLE001
        # Technische Details server-seitig loggen, dem Frontend nur eine
        # generische Meldung zeigen (keine Pfade/Stacktraces im processing_error).
        logger.exception("Verarbeitung der Version %s fehlgeschlagen", vid)
        new_status = ProcessingStatus.failed
        error = "Verarbeitung fehlgeschlagen"

    # 3) Ergebnis persistieren.
    with session_scope() as session:
        version = session.get(DocumentVersion, vid)
        if version is None:
            return "missing"
        version.processing_status = new_status
        version.processing_error = error
        # Datenminimierung (Art. 5(1c)/32): Die Extraktion validiert nur die
        # Lesbarkeit der Datei; der Volltext wird NICHT unverschluesselt in der
        # DB gespeichert. Reaktivieren erst mit Volltextsuche (dann als tsvector).
        version.extracted_text = None
        version.processed_at = datetime.now(UTC)
        session.add(version)

    return new_status.value
