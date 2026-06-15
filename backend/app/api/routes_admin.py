"""Admin-/Compliance-Endpunkte (alle erfordern Superadmin)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import StreamingResponse

from app.core.deps import SessionDep, SuperadminDep, get_client_ip
from app.core.errors import not_found
from app.core.tasks import enqueue_export_user_data
from app.schemas.admin import (
    AdminUserCreate,
    AdminUserOut,
    AuditLogOut,
    ExportOut,
    LegalHoldSetIn,
    RetentionSetIn,
)
from app.api.routes_documents import build_detail
from app.schemas.common import Page
from app.schemas.document import DocumentDetailOut
from app.services import compliance_service, document_service
from dms_core.audit import write_audit_log
from dms_core.enums import AuditAction, ExportStatus
from dms_core.models.audit import AuditLog
from dms_core.storage import get_export_storage

router = APIRouter(prefix="/admin", tags=["admin"])


def _audit_out(row: AuditLog) -> AuditLogOut:
    return AuditLogOut(
        id=row.id,
        actor_user_id=row.actor_user_id,
        action=row.action,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        project_id=row.project_id,
        ip_address=row.ip_address,
        metadata=row.metadata_,
        created_at=row.created_at,
    )


@router.get("/users", response_model=Page[AdminUserOut])
def list_users(
    _admin: SuperadminDep,
    session: SessionDep,
    limit: int = Query(default=50, le=100, ge=1),
    offset: int = Query(default=0, ge=0),
) -> Page[AdminUserOut]:
    users, total = compliance_service.list_users(session, limit=limit, offset=offset)
    return Page(
        items=[AdminUserOut.model_validate(u) for u in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/users", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: AdminUserCreate, admin: SuperadminDep, session: SessionDep, request: Request
) -> AdminUserOut:
    user = compliance_service.create_user(
        session,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        is_superadmin=body.is_superadmin,
        actor=admin,
        ip=get_client_ip(request),
    )
    session.commit()
    session.refresh(user)
    return AdminUserOut.model_validate(user)


@router.delete("/users/{user_id}", response_model=AdminUserOut)
def anonymize_user(
    user_id: uuid.UUID, admin: SuperadminDep, session: SessionDep, request: Request
) -> AdminUserOut:
    user = compliance_service.anonymize_user(
        session, target_user_id=user_id, actor=admin, ip=get_client_ip(request)
    )
    session.commit()
    session.refresh(user)
    return AdminUserOut.model_validate(user)


@router.get("/audit-logs", response_model=Page[AuditLogOut])
def list_audit_logs(
    _admin: SuperadminDep,
    session: SessionDep,
    limit: int = Query(default=50, le=100, ge=1),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    actor_user_id: uuid.UUID | None = Query(default=None),
) -> Page[AuditLogOut]:
    rows, total = compliance_service.list_audit_logs(
        session,
        limit=limit,
        offset=offset,
        action=action,
        project_id=project_id,
        actor_user_id=actor_user_id,
    )
    return Page(
        items=[_audit_out(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post(
    "/users/{user_id}/export", response_model=ExportOut, status_code=status.HTTP_201_CREATED
)
def create_user_export(
    user_id: uuid.UUID, admin: SuperadminDep, session: SessionDep, request: Request
) -> ExportOut:
    export = compliance_service.create_user_export(
        session, subject_user_id=user_id, actor=admin, ip=get_client_ip(request)
    )
    session.commit()
    session.refresh(export)
    enqueue_export_user_data(export.id)
    return ExportOut.model_validate(export)


@router.get("/exports", response_model=Page[ExportOut])
def list_exports(
    _admin: SuperadminDep,
    session: SessionDep,
    limit: int = Query(default=50, le=100, ge=1),
    offset: int = Query(default=0, ge=0),
) -> Page[ExportOut]:
    rows, total = compliance_service.list_exports(session, limit=limit, offset=offset)
    return Page(
        items=[ExportOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/exports/{export_id}/download")
def download_export(
    export_id: uuid.UUID, admin: SuperadminDep, session: SessionDep, request: Request
) -> StreamingResponse:
    export = compliance_service.get_export_or_404(session, export_id)
    if export.status != ExportStatus.ready or not export.storage_key:
        raise not_found("Export ist nicht (mehr) verfuegbar")
    expires = export.expires_at
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires and expires < datetime.now(UTC):
        raise not_found("Export ist abgelaufen")

    write_audit_log(
        session,
        action=AuditAction.compliance_user_export_downloaded,
        entity_type="user_export",
        actor_user_id=admin.id,
        entity_id=export.id,
        ip_address=get_client_ip(request),
        metadata={"subject_user_id": str(export.subject_user_id)},
    )
    session.commit()
    filename = f"export-{export.subject_user_id}.json"
    return StreamingResponse(
        get_export_storage().open_stream(export.storage_key),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ---- Dokumentbezogene Compliance-Aktionen (Superadmin, projektunabhaengig) ----

@router.post("/documents/{document_id}/set-retention", response_model=DocumentDetailOut)
def set_retention(
    document_id: uuid.UUID,
    body: RetentionSetIn,
    admin: SuperadminDep,
    session: SessionDep,
    request: Request,
) -> DocumentDetailOut:
    document = compliance_service.get_document_or_404(session, document_id)
    compliance_service.set_retention(
        session,
        document=document,
        retention_until=body.retention_until,
        actor=admin,
        ip=get_client_ip(request),
    )
    session.commit()
    session.refresh(document)
    current = document_service.get_current_version(session, document.id)
    return build_detail(document, current)


@router.post("/documents/{document_id}/legal-hold", response_model=DocumentDetailOut)
def set_legal_hold(
    document_id: uuid.UUID,
    body: LegalHoldSetIn,
    admin: SuperadminDep,
    session: SessionDep,
    request: Request,
) -> DocumentDetailOut:
    document = compliance_service.get_document_or_404(session, document_id)
    compliance_service.set_legal_hold(
        session,
        document=document,
        legal_hold=body.legal_hold,
        actor=admin,
        ip=get_client_ip(request),
    )
    session.commit()
    session.refresh(document)
    current = document_service.get_current_version(session, document.id)
    return build_detail(document, current)
