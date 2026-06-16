"""Dokument- und Versions-Geschaeftslogik inkl. sicherem Upload."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from fastapi import UploadFile
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.errors import ApiError, bad_request
from app.schemas.common import paginate
from dms_core.audit import write_audit_log
from dms_core.config import settings
from dms_core.enums import AuditAction, DocumentStatus, ProcessingStatus
from dms_core.files import HEAD_BYTES, HashingLimitedReader, UploadTooLarge, guess_mime_from_bytes
from dms_core.models.document import Document, DocumentVersion
from dms_core.models.project import Project, ProjectMember
from dms_core.models.user import User
from dms_core.storage import get_storage


@dataclass
class StoredBlob:
    storage_key: str
    file_name: str
    mime_type: str
    size_bytes: int
    sha256: str


def _sanitize_filename(name: str | None) -> str:
    base = os.path.basename(name or "").strip() or "datei"
    # Steuerzeichen/Slashes entfernen, Laenge begrenzen.
    cleaned = "".join(c for c in base if c.isprintable() and c not in "/\\").strip()
    return (cleaned or "datei")[:400]


def _store_upload(
    upload: UploadFile, *, document_id: uuid.UUID, version_id: uuid.UUID
) -> StoredBlob:
    src = upload.file  # synchrones File-Objekt (SpooledTemporaryFile)
    head = src.read(HEAD_BYTES)
    if not head:
        raise bad_request("Leere Datei", code="empty_file")
    mime = guess_mime_from_bytes(head)
    if mime not in settings.allowed_mime_set:
        raise ApiError(415, "unsupported_media_type", f"Dateityp nicht erlaubt: {mime}")
    src.seek(0)

    storage_key = f"{document_id}/{version_id}"
    reader = HashingLimitedReader(src, max_bytes=settings.max_upload_bytes)
    try:
        get_storage().save(storage_key, reader)  # type: ignore[arg-type]
    except UploadTooLarge as exc:
        raise ApiError(
            413,
            "payload_too_large",
            f"Datei groesser als erlaubt ({settings.max_upload_bytes} Bytes)",
        ) from exc

    return StoredBlob(
        storage_key=storage_key,
        file_name=_sanitize_filename(upload.filename),
        mime_type=mime,
        size_bytes=reader.size,
        sha256=reader.hexdigest(),
    )


def _escape_like(value: str) -> str:
    """ILIKE-Metacharaktere escapen, damit der Suchbegriff literal gematcht wird."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _new_version(
    *,
    version_id: uuid.UUID,
    document_id: uuid.UUID,
    version_number: int,
    blob: StoredBlob,
    actor: User,
) -> DocumentVersion:
    return DocumentVersion(
        id=version_id,
        document_id=document_id,
        version_number=version_number,
        file_name=blob.file_name,
        file_hash=blob.sha256,
        storage_key=blob.storage_key,
        mime_type=blob.mime_type,
        size_bytes=blob.size_bytes,
        processing_status=ProcessingStatus.uploaded,
        created_by=actor.id,
    )


def create_document_with_version(
    session: Session,
    *,
    project_id: uuid.UUID,
    title: str,
    description: str | None,
    category: str | None,
    upload: UploadFile,
    actor: User,
    ip: str | None,
) -> tuple[Document, DocumentVersion]:
    retention_until = (
        date.today() + timedelta(days=settings.default_retention_days)
        if settings.default_retention_days > 0
        else None
    )
    document = Document(
        id=uuid.uuid4(),
        project_id=project_id,
        title=title,
        description=description,
        category=category,
        status=DocumentStatus.active,
        created_by=actor.id,
        retention_until=retention_until,
    )
    version_id = uuid.uuid4()
    blob = _store_upload(upload, document_id=document.id, version_id=version_id)
    version = _new_version(
        version_id=version_id,
        document_id=document.id,
        version_number=1,
        blob=blob,
        actor=actor,
    )
    session.add(document)
    session.add(version)
    session.flush()

    write_audit_log(
        session,
        action=AuditAction.document_uploaded,
        entity_type="document",
        actor_user_id=actor.id,
        entity_id=document.id,
        project_id=project_id,
        ip_address=ip,
        metadata={"title": title, "file_name": blob.file_name},
    )
    write_audit_log(
        session,
        action=AuditAction.document_version_created,
        entity_type="document_version",
        actor_user_id=actor.id,
        entity_id=version.id,
        project_id=project_id,
        ip_address=ip,
        metadata={"version_number": 1},
    )
    return document, version


def add_version(
    session: Session,
    *,
    document: Document,
    upload: UploadFile,
    actor: User,
    ip: str | None,
) -> DocumentVersion:
    # Race Condition vermeiden: parallele Uploads desselben Dokuments wuerden sonst
    # dieselbe version_number berechnen (MAX+1) -> Unique-Verletzung + verwaister Blob.
    # FOR UPDATE sperrt die Document-Zeile, sodass Postgres die Uploads serialisiert.
    # Die Sperre haelt bis zum Commit der Request-Transaktion (Commit liegt in der Route).
    session.exec(select(Document).where(Document.id == document.id).with_for_update()).one()
    max_num = session.exec(
        select(func.max(DocumentVersion.version_number)).where(
            DocumentVersion.document_id == document.id
        )
    ).one()
    next_num = (max_num or 0) + 1

    version_id = uuid.uuid4()
    blob = _store_upload(upload, document_id=document.id, version_id=version_id)
    version = _new_version(
        version_id=version_id,
        document_id=document.id,
        version_number=next_num,
        blob=blob,
        actor=actor,
    )
    session.add(version)
    session.flush()

    write_audit_log(
        session,
        action=AuditAction.document_version_created,
        entity_type="document_version",
        actor_user_id=actor.id,
        entity_id=version.id,
        project_id=document.project_id,
        ip_address=ip,
        metadata={"version_number": next_num},
    )
    return version


def get_current_version(session: Session, document_id: uuid.UUID) -> DocumentVersion | None:
    return session.exec(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    ).first()


def list_versions(session: Session, document_id: uuid.UUID) -> list[DocumentVersion]:
    return list(
        session.exec(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
        ).all()
    )


def list_documents(
    session: Session,
    *,
    project_id: uuid.UUID,
    limit: int,
    offset: int,
    status: str | None = None,
    search: str | None = None,
) -> tuple[list[dict], int]:
    conditions = [Document.project_id == project_id]
    if status:
        # Exakter Status (auch 'deleted' -> Papierkorb, 'archived' -> Archiv).
        conditions.append(Document.status == status)
    else:
        # Default: aktive + archivierte, ohne Papierkorb.
        conditions.append(Document.status != DocumentStatus.deleted)
    if search:
        escaped = _escape_like(search)
        conditions.append(Document.title.ilike(f"%{escaped}%", escape="\\"))

    docs, total = paginate(
        session,
        select(Document).where(*conditions).order_by(Document.created_at.desc()),
        limit=limit,
        offset=offset,
    )

    # Performance: nur die jeweils neueste Version pro Dokument laden (DISTINCT ON)
    # statt aller Versionen -> O(docs) statt O(docs x versions).
    doc_ids = [d.id for d in docs]
    latest_by_doc: dict[uuid.UUID, DocumentVersion] = {}
    count_by_doc: dict[uuid.UUID, int] = {}
    if doc_ids:
        for v in session.exec(
            select(DocumentVersion)
            .where(DocumentVersion.document_id.in_(doc_ids))
            .distinct(DocumentVersion.document_id)
            .order_by(
                DocumentVersion.document_id,
                DocumentVersion.version_number.desc(),
            )
        ).all():
            latest_by_doc[v.document_id] = v
        # version_count separat als Aggregat (zeigt Gesamtzahl Versionen).
        for doc_id, cnt in session.exec(
            select(DocumentVersion.document_id, func.count())
            .where(DocumentVersion.document_id.in_(doc_ids))
            .group_by(DocumentVersion.document_id)
        ).all():
            count_by_doc[doc_id] = cnt

    items: list[dict] = []
    for d in docs:
        latest = latest_by_doc.get(d.id)
        items.append(
            {
                "id": d.id,
                "title": d.title,
                "category": d.category,
                "status": d.status,
                "latest_version_number": latest.version_number if latest else None,
                "latest_processing_status": latest.processing_status if latest else None,
                "version_count": count_by_doc.get(d.id, 0),
                "created_at": d.created_at,
                "updated_at": d.updated_at,
                "deleted_at": d.deleted_at,
                "purge_after": d.purge_after,
                "legal_hold": d.legal_hold,
                "retention_until": d.retention_until,
            }
        )
    return items, total


def update_metadata(
    session: Session,
    *,
    document: Document,
    title: str | None,
    description: str | None,
    category: str | None,
    status: str | None,
    actor: User,
    ip: str | None,
) -> Document:
    changed: dict[str, object] = {}
    if title is not None:
        document.title = title
        changed["title"] = title
    if description is not None:
        document.description = description
        # Bewusst kein Wert: Beschreibung kann PII enthalten (Datenminimierung Art. 5)
        changed["description"] = True
    if category is not None:
        document.category = category
        changed["category"] = category
    if status is not None:
        document.status = status
        changed["status"] = status

    session.add(document)
    write_audit_log(
        session,
        action=AuditAction.document_metadata_updated,
        entity_type="document",
        actor_user_id=actor.id,
        entity_id=document.id,
        project_id=document.project_id,
        ip_address=ip,
        metadata={"fields": list(changed.keys())},
    )
    return document


def reprocess_version(
    session: Session,
    *,
    version: DocumentVersion,
    project_id: uuid.UUID,
    actor: User,
    ip: str | None,
) -> DocumentVersion:
    """Setzt eine Version zurueck in die Pipeline (z.B. nach failed/quarantined)."""
    version.processing_status = ProcessingStatus.uploaded
    version.processing_error = None
    version.processed_at = None
    session.add(version)
    write_audit_log(
        session,
        action=AuditAction.document_version_reprocessed,
        entity_type="document_version",
        actor_user_id=actor.id,
        entity_id=version.id,
        project_id=project_id,
        ip_address=ip,
        metadata={"version_number": version.version_number},
    )
    return version


def recent_documents(session: Session, *, user: User, limit: int = 10) -> list[dict]:
    """Projektuebergreifend die zuletzt aktualisierten Dokumente aus Projekten,
    in denen der User Mitglied ist (ohne Papierkorb)."""
    rows = session.exec(
        select(Document, Project.name)
        .join(ProjectMember, ProjectMember.project_id == Document.project_id)
        .join(Project, Project.id == Document.project_id)
        .where(
            ProjectMember.user_id == user.id,
            Document.status != DocumentStatus.deleted,
            Project.status != "deleted",
        )
        .order_by(Document.updated_at.desc())
        .limit(limit)
    ).all()

    docs = [d for d, _name in rows]
    doc_ids = [d.id for d in docs]
    latest_status: dict[uuid.UUID, str] = {}
    if doc_ids:
        # Nur die neueste Version pro Dokument laden (DISTINCT ON), nicht alle.
        for v in session.exec(
            select(DocumentVersion)
            .where(DocumentVersion.document_id.in_(doc_ids))
            .distinct(DocumentVersion.document_id)
            .order_by(
                DocumentVersion.document_id,
                DocumentVersion.version_number.desc(),
            )
        ).all():
            latest_status[v.document_id] = v.processing_status

    return [
        {
            "id": d.id,
            "title": d.title,
            "project_id": d.project_id,
            "project_name": name,
            "status": d.status,
            "latest_processing_status": latest_status.get(d.id),
            "updated_at": d.updated_at,
        }
        for d, name in rows
    ]
