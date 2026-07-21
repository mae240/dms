"""Wartungs-/Compliance-Kernlogik (Session + Storage als Parameter).

Bewusst hier (statt im Worker), damit Backend-Tests die kritische Logik
— insbesondere 'legal_hold blockt Purge' — mit einer Test-Session und einem
Test-Storage direkt pruefen koennen. Die Funktionen committen NICHT; das
uebernimmt der aufrufende Scope (Worker: session_scope).
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, case, func, or_, update
from sqlalchemy.orm import aliased
from sqlmodel import Session, select

from dms_core.audit import write_audit_log
from dms_core.config import settings
from dms_core.enums import AuditAction, DocumentStatus, ExportStatus
from dms_core.models.audit import AuditLog
from dms_core.models.document import Document, DocumentVersion
from dms_core.models.export import UserExport
from dms_core.models.project import Project, ProjectMember, RetentionRule
from dms_core.models.user import User
from dms_core.storage import StorageBackend, StorageError

logger = logging.getLogger(__name__)

PURGE_BATCH = 200


def _delete_blob(storage: StorageBackend, key: str | None) -> None:
    if not key:
        return
    # idempotent: fehlende/fehlerhafte Blobs blockieren den Purge nicht
    with contextlib.suppress(StorageError):
        storage.delete(key)


def purge_deleted_documents(session: Session, storage: StorageBackend) -> int:
    """Loescht endgueltig: status=deleted, NICHT legal_hold, purge_after erreicht,
    retention_until abgelaufen/leer. Blobs zuerst, dann Zeilen, plus Audit.

    Gebatcht (LIMIT-Schleife) wie die anderen Wartungsjobs, damit ein Rueckstau
    > PURGE_BATCH in einem Lauf vollstaendig abgearbeitet wird. Geloeschte Zeilen
    werden nicht erneut selektiert -> Schleife terminiert.
    """
    now = datetime.now(UTC)
    purged = 0
    while True:
        candidates = session.exec(
            select(Document)
            .where(
                Document.status == DocumentStatus.deleted,
                Document.legal_hold.is_(False),
                Document.purge_after.is_not(None),
                Document.purge_after <= now,
                or_(
                    Document.retention_until.is_(None),
                    Document.retention_until <= date.today(),
                ),
            )
            .limit(PURGE_BATCH)
        ).all()
        if not candidates:
            break

        # N+1 vermeiden: alle Versionen des Batches in EINEM Query laden und im
        # Speicher nach document_id gruppieren.
        doc_ids = [doc.id for doc in candidates]
        versions_by_doc: dict[uuid.UUID, list[DocumentVersion]] = {doc.id: [] for doc in candidates}
        for v in session.exec(
            select(DocumentVersion).where(DocumentVersion.document_id.in_(doc_ids))
        ).all():
            versions_by_doc[v.document_id].append(v)

        for doc in candidates:
            if doc.legal_hold:  # Defense in Depth (zusaetzlich zur WHERE-Clause)
                continue
            versions = versions_by_doc.get(doc.id, [])
            for v in versions:
                _delete_blob(storage, v.storage_key)
                _delete_blob(storage, v.preview_storage_key)

            write_audit_log(
                session,
                action=AuditAction.compliance_document_purged,
                entity_type="document",
                actor_user_id=None,
                entity_id=doc.id,
                project_id=doc.project_id,
                metadata={"versions": len(versions), "title": doc.title},
            )
            session.delete(doc)  # CASCADE -> Versions-Zeilen
            purged += 1

        session.flush()
        if len(candidates) < PURGE_BATCH:
            break
    return purged


def auto_soft_delete_expired(session: Session, *, now: datetime | None = None) -> int:
    """Soft-deletet aktive Dokumente gemaess Retention-Regeln (Maximal-Aufbewahrung).

    Aufloesung: Kategorie-Regel schlaegt Projekt-Default (category=NULL). Eine
    Kategorie-Regel mit max_days=NULL ist 'exempt'. Respektiert legal_hold und
    die Mindest-Aufbewahrung (retention_until). Gechunked via PURGE_BATCH.
    """
    now = now or datetime.now(UTC)
    today = now.date()
    rc = aliased(RetentionRule)  # Kategorie-spezifisch
    rp = aliased(RetentionRule)  # Projekt-Default (category IS NULL)
    effective = case((rc.id.is_not(None), rc.max_days), else_=rp.max_days)

    purge_after = now + timedelta(days=settings.purge_grace_days)
    # Gebatcht (LIMIT-Schleife), damit ein Rueckstau > PURGE_BATCH vollstaendig
    # abgearbeitet wird (gleiches Muster wie purge_deleted_documents). Soft-gedeletete
    # Dokumente verlassen status=active und werden nicht erneut selektiert -> Schleife
    # terminiert.
    total = 0
    while True:
        candidates = session.exec(
            select(Document)
            .join(Project, Project.id == Document.project_id)
            .outerjoin(
                rc, and_(rc.project_id == Document.project_id, rc.category == Document.category)
            )
            .outerjoin(rp, and_(rp.project_id == Document.project_id, rp.category.is_(None)))
            .where(
                Document.status == DocumentStatus.active,
                Document.legal_hold.is_(False),
                effective.is_not(None),
                # PG make_interval(years, months, weeks, days)
                Document.created_at < now - func.make_interval(0, 0, 0, effective),
                or_(Document.retention_until.is_(None), Document.retention_until <= today),
            )
            .limit(PURGE_BATCH)
        ).all()
        if not candidates:
            break
        for doc in candidates:
            doc.status = DocumentStatus.deleted
            doc.deleted_at = now
            doc.purge_after = purge_after
            session.add(doc)
            write_audit_log(
                session,
                action=AuditAction.document_auto_expired,
                entity_type="document",
                actor_user_id=None,
                entity_id=doc.id,
                project_id=doc.project_id,
                metadata={"reason": "retention_max"},
            )
        session.flush()
        total += len(candidates)
        if len(candidates) < PURGE_BATCH:
            break
    return total


def build_export_payload(session: Session, subject_id: uuid.UUID) -> dict:
    user = session.get(User, subject_id)
    if user is None:
        raise ValueError("Subjekt-User nicht gefunden")

    memberships = session.exec(
        select(ProjectMember).where(ProjectMember.user_id == subject_id)
    ).all()
    documents = session.exec(select(Document).where(Document.created_by == subject_id)).all()
    versions = session.exec(
        select(DocumentVersion).where(DocumentVersion.created_by == subject_id)
    ).all()

    # Audit-Events koennen pro Subjekt sehr zahlreich sein -> gebatcht einlesen
    # (LIMIT/OFFSET via stabiler id-Sortierung) und inkrementell in die Payload
    # schreiben, statt alle Zeilen gleichzeitig zu materialisieren. Das Ausgabe-
    # Format (Liste 'audit_events') bleibt unveraendert.
    audit_events: list[dict] = []
    offset = 0
    while True:
        batch = session.exec(
            select(AuditLog)
            .where(AuditLog.actor_user_id == subject_id)
            .order_by(AuditLog.id)
            .limit(PURGE_BATCH)
            .offset(offset)
        ).all()
        if not batch:
            break
        audit_events.extend(
            {
                "action": a.action,
                "entity_type": a.entity_type,
                "entity_id": a.entity_id,
                "project_id": a.project_id,
                "created_at": a.created_at,
            }
            for a in batch
        )
        offset += len(batch)
        if len(batch) < PURGE_BATCH:
            break

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "is_superadmin": user.is_superadmin,
            "is_anonymized": user.is_anonymized,
            "created_at": user.created_at,
        },
        "project_memberships": [
            {"project_id": m.project_id, "role": m.role, "created_at": m.created_at}
            for m in memberships
        ],
        "documents_created": [
            {
                "id": d.id,
                "project_id": d.project_id,
                "title": d.title,
                "category": d.category,
                "status": d.status,
                "created_at": d.created_at,
            }
            for d in documents
        ],
        "versions_created": [
            {
                "id": v.id,
                "document_id": v.document_id,
                "version_number": v.version_number,
                "file_name": v.file_name,
                "mime_type": v.mime_type,
                "size_bytes": v.size_bytes,
                "processing_status": v.processing_status,
                "created_at": v.created_at,
            }
            for v in versions
        ],
        "audit_events": audit_events,
    }


def produce_export(session: Session, export_id: uuid.UUID, export_storage: StorageBackend) -> str:
    """Erzeugt die JSON-Export-Datei und setzt den Status. Idempotent."""
    export = session.get(UserExport, export_id)
    if export is None:
        return "missing"
    if export.status != ExportStatus.pending:
        return "already_processed"
    try:
        payload = build_export_payload(session, export.subject_user_id)
        data = json.dumps(payload, ensure_ascii=False, default=str, indent=2).encode("utf-8")
        key = f"{export_id}.json"
        export_storage.save(key, io.BytesIO(data))
        export.status = ExportStatus.ready
        export.storage_key = key
        export.completed_at = datetime.now(UTC)
        session.add(export)
        session.flush()
        return "ready"
    except Exception:  # noqa: BLE001
        # Technische Details nur server-seitig loggen, nie an den Client/Admin
        # zurueckgeben (Pfad-/Detail-Leak vermeiden).
        logger.exception("Export %s fehlgeschlagen", export_id)
        export.status = ExportStatus.failed
        export.error = "Export fehlgeschlagen"
        session.add(export)
        session.flush()
        return "failed"


def cleanup_expired_exports(session: Session, export_storage: StorageBackend) -> int:
    now = datetime.now(UTC)
    # Gebatcht (LIMIT-Schleife), damit nicht unbegrenzt viele Zeilen in einer
    # Transaktion gesperrt werden (gleiche Konstante wie purge_deleted_documents).
    total = 0
    while True:
        expired = session.exec(
            select(UserExport)
            .where(
                UserExport.expires_at.is_not(None),
                UserExport.expires_at <= now,
                UserExport.status != ExportStatus.expired,
            )
            .limit(PURGE_BATCH)
        ).all()
        if not expired:
            break
        for export in expired:
            _delete_blob(export_storage, export.storage_key)
            export.status = ExportStatus.expired
            export.storage_key = None
            session.add(export)
        session.flush()
        total += len(expired)
        if len(expired) < PURGE_BATCH:
            break
    return total


def rewrap_blobs(session: Session, storage: object) -> dict[str, int]:
    """Schluesselt alle Blobs auf die aktive Key-Version um. `storage` muss
    rewrap(key)->bool unterstuetzen (EncryptedStorageBackend). Idempotent.

    Duck-typed auf rewrap: ein nicht-verschluesselndes Backend ist ein No-Op,
    damit dms_core nicht hart von EncryptedStorageBackend abhaengt."""
    if not hasattr(storage, "rewrap"):
        return {"rewrapped": 0, "skipped": 0, "errors": 0}
    rewrapped = skipped = errors = 0
    # Gebatcht via stabiler Sortierung (id) + LIMIT/OFFSET, damit nicht alle
    # storage_keys auf einmal in den RAM geladen werden (gleiches Batch-Prinzip
    # wie purge_deleted_documents). rewrap aendert keine Selektionskriterien,
    # daher ist OFFSET-Paging hier korrekt.
    offset = 0
    while True:
        keys = session.exec(
            select(DocumentVersion.storage_key)
            .order_by(DocumentVersion.id)
            .limit(PURGE_BATCH)
            .offset(offset)
        ).all()
        if not keys:
            break
        for key in keys:
            try:
                if storage.rewrap(key):
                    rewrapped += 1
                else:
                    skipped += 1
            except StorageError:
                errors += 1  # einzelner Blob blockiert die Rotation nicht
        offset += len(keys)
        if len(keys) < PURGE_BATCH:
            break
    return {"rewrapped": rewrapped, "skipped": skipped, "errors": errors}


def cleanup_audit_ip(session: Session, retention_days: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    # Nur ip_address -> NULL; der Audit-Trigger erlaubt genau diese Schwaerzung.
    # Gebatcht via Subquery auf id, damit ein langer Lock auf vielen Zeilen
    # vermieden wird (Schleife bis keine Zeilen mehr betroffen sind).
    total = 0
    while True:
        batch_ids = session.exec(
            select(AuditLog.id)
            .where(AuditLog.created_at < cutoff, AuditLog.ip_address.is_not(None))
            .limit(PURGE_BATCH)
        ).all()
        if not batch_ids:
            break
        result = session.exec(
            update(AuditLog).where(AuditLog.id.in_(batch_ids)).values(ip_address=None)
        )
        affected = int(result.rowcount or 0)
        total += affected
        if affected < PURGE_BATCH:
            break
    return total
