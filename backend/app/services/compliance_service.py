"""Compliance-Geschaeftslogik: Soft-Delete/Restore, Retention, Legal Hold,
User-Export, Audit-Einsicht, User-Anonymisierung (Art. 17).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session, select

from app.core.errors import bad_request, conflict, not_found
from app.schemas.common import paginate
from dms_core.audit import write_audit_log
from dms_core.config import settings
from dms_core.enums import AuditAction, DocumentStatus, ExportStatus
from dms_core.models.audit import AuditLog
from dms_core.models.document import Document
from dms_core.models.export import UserExport
from dms_core.models.project import ProjectMember
from dms_core.models.user import RefreshToken, User
from dms_core.security import hash_password


def get_document_or_404(session: Session, document_id: uuid.UUID) -> Document:
    doc = session.get(Document, document_id)
    if doc is None:
        raise not_found("Dokument nicht gefunden")
    return doc


# ---- Soft-Delete / Restore (projektgebunden) ----


def soft_delete_document(
    session: Session, *, document: Document, actor: User, ip: str | None
) -> Document:
    if document.status == DocumentStatus.deleted:
        raise bad_request("Dokument ist bereits geloescht", code="already_deleted")
    if document.legal_hold:
        raise conflict(
            "Dokument steht unter Legal Hold und kann nicht geloescht werden", code="legal_hold"
        )
    # Mindest-Aufbewahrung (G-3): solange retention_until in der Zukunft liegt, ist
    # kein Loeschen erlaubt — auch legal_hold umgeht das nicht.
    if document.retention_until is not None and document.retention_until > date.today():
        raise conflict(
            "Mindest-Aufbewahrungsfrist noch nicht abgelaufen", code="retention_active"
        )

    now = datetime.now(UTC)
    document.status = DocumentStatus.deleted
    document.deleted_at = now
    document.deleted_by = actor.id
    document.purge_after = now + timedelta(days=settings.purge_grace_days)
    session.add(document)
    write_audit_log(
        session,
        action=AuditAction.document_deleted,
        entity_type="document",
        actor_user_id=actor.id,
        entity_id=document.id,
        project_id=document.project_id,
        ip_address=ip,
        metadata={"purge_after": document.purge_after.isoformat()},
    )
    return document


def restore_document(
    session: Session, *, document: Document, actor: User, ip: str | None
) -> Document:
    if document.status != DocumentStatus.deleted:
        raise bad_request(
            "Nur geloeschte Dokumente koennen wiederhergestellt werden", code="not_deleted"
        )
    document.status = DocumentStatus.active
    document.deleted_at = None
    document.deleted_by = None
    document.purge_after = None  # WICHTIG: sonst purged ein restauriertes Doc spaeter
    session.add(document)
    write_audit_log(
        session,
        action=AuditAction.document_restored,
        entity_type="document",
        actor_user_id=actor.id,
        entity_id=document.id,
        project_id=document.project_id,
        ip_address=ip,
    )
    return document


# ---- Retention / Legal Hold (superadmin) ----


def set_retention(
    session: Session,
    *,
    document: Document,
    retention_until: date | None,
    actor: User,
    ip: str | None,
) -> Document:
    document.retention_until = retention_until
    session.add(document)
    write_audit_log(
        session,
        action=AuditAction.compliance_retention_set,
        entity_type="document",
        actor_user_id=actor.id,
        entity_id=document.id,
        project_id=document.project_id,
        ip_address=ip,
        metadata={"retention_until": retention_until.isoformat() if retention_until else None},
    )
    return document


def set_legal_hold(
    session: Session, *, document: Document, legal_hold: bool, actor: User, ip: str | None
) -> Document:
    document.legal_hold = legal_hold
    session.add(document)
    write_audit_log(
        session,
        action=AuditAction.compliance_legal_hold_set,
        entity_type="document",
        actor_user_id=actor.id,
        entity_id=document.id,
        project_id=document.project_id,
        ip_address=ip,
        metadata={"legal_hold": legal_hold},
    )
    return document


# ---- Admin-Listen ----


def create_user(
    session: Session,
    *,
    email: str,
    password: str,
    full_name: str,
    is_superadmin: bool,
    actor: User,
    ip: str | None,
) -> User:
    if session.exec(select(User).where(User.email == email)).first() is not None:
        raise conflict("E-Mail ist bereits vergeben", code="email_taken")

    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        is_active=True,
        is_superadmin=is_superadmin,
    )
    session.add(user)
    session.flush()
    write_audit_log(
        session,
        action=AuditAction.user_created,
        entity_type="user",
        actor_user_id=actor.id,
        entity_id=user.id,
        ip_address=ip,
        metadata={"is_superadmin": is_superadmin},
    )
    return user


def list_users(session: Session, *, limit: int, offset: int) -> tuple[list[User], int]:
    return paginate(
        session, select(User).order_by(User.created_at.asc()), limit=limit, offset=offset
    )


def list_audit_logs(
    session: Session,
    *,
    limit: int,
    offset: int,
    action: str | None = None,
    project_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> tuple[list[AuditLog], int]:
    conditions = []
    if action:
        conditions.append(AuditLog.action == action)
    if project_id:
        conditions.append(AuditLog.project_id == project_id)
    if actor_user_id:
        conditions.append(AuditLog.actor_user_id == actor_user_id)

    return paginate(
        session,
        select(AuditLog).where(*conditions).order_by(AuditLog.created_at.desc()),
        limit=limit,
        offset=offset,
    )


# ---- User-Export (Art. 15/20) ----


def create_user_export(
    session: Session, *, subject_user_id: uuid.UUID, actor: User, ip: str | None
) -> UserExport:
    subject = session.get(User, subject_user_id)
    if subject is None:
        raise not_found("Benutzer nicht gefunden")

    export = UserExport(
        subject_user_id=subject_user_id,
        requested_by=actor.id,
        status=ExportStatus.pending,
        expires_at=datetime.now(UTC) + timedelta(hours=settings.export_ttl_hours),
    )
    session.add(export)
    session.flush()
    write_audit_log(
        session,
        action=AuditAction.compliance_user_export_created,
        entity_type="user_export",
        actor_user_id=actor.id,
        entity_id=export.id,
        ip_address=ip,
        metadata={"subject_user_id": str(subject_user_id)},
    )
    return export


def list_exports(session: Session, *, limit: int, offset: int) -> tuple[list[UserExport], int]:
    return paginate(
        session,
        select(UserExport).order_by(UserExport.created_at.desc()),
        limit=limit,
        offset=offset,
    )


def get_export_or_404(session: Session, export_id: uuid.UUID) -> UserExport:
    export = session.get(UserExport, export_id)
    if export is None:
        raise not_found("Export nicht gefunden")
    return export


# ---- User-Anonymisierung (Art. 17) ----


def anonymize_user(
    session: Session, *, target_user_id: uuid.UUID, actor: User, ip: str | None
) -> User:
    if target_user_id == actor.id:
        raise bad_request("Das eigene Konto kann nicht anonymisiert werden", code="cannot_self")

    target = session.get(User, target_user_id)
    if target is None:
        raise not_found("Benutzer nicht gefunden")
    if target.is_anonymized:
        raise bad_request("Benutzer ist bereits anonymisiert", code="already_anonymized")

    # PII entfernen, Konto deaktivieren.
    target.email = f"anonymized-{target.id}@deleted.invalid"
    target.full_name = ""
    target.hashed_password = "!"  # unbrauchbarer Hash -> kein Login mehr moeglich
    target.is_active = False
    target.is_anonymized = True
    target.is_superadmin = False
    session.add(target)

    # Aktive Refresh-Tokens widerrufen.
    now = datetime.now(UTC)
    for token in session.exec(
        select(RefreshToken).where(
            RefreshToken.user_id == target_user_id, RefreshToken.revoked_at.is_(None)
        )
    ).all():
        token.revoked_at = now
        session.add(token)

    # Projekt-Mitgliedschaften entfernen (Zugriff entziehen).
    for member in session.exec(
        select(ProjectMember).where(ProjectMember.user_id == target_user_id)
    ).all():
        session.delete(member)

    write_audit_log(
        session,
        action=AuditAction.user_anonymized,
        entity_type="user",
        actor_user_id=actor.id,
        entity_id=target_user_id,
        ip_address=ip,
    )
    return target
