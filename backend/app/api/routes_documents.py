"""Dokument- und Versions-Endpunkte (inkl. sichere Downloads)."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.core.deps import SessionDep, get_client_ip
from app.core.errors import forbidden, not_found
from app.core.project_access import (
    DocumentContext,
    ProjectContext,
    VersionContext,
    require_document_role,
    require_project_role,
    require_version_access,
)
from app.core.tasks import enqueue_process_version
from app.schemas.common import Page
from app.schemas.document import (
    DocumentDetailOut,
    DocumentListItem,
    DocumentMetadataPatch,
    VersionOut,
)
from app.services import compliance_service, document_service
from dms_core.audit import write_audit_log
from dms_core.enums import (
    AuditAction,
    DocumentStatus,
    ProcessingStatus,
    ProjectRole,
    role_satisfies,
)
from dms_core.models.document import Document, DocumentVersion
from dms_core.storage import get_storage

router = APIRouter(tags=["documents"])

ProjViewer = Annotated[ProjectContext, Depends(require_project_role(ProjectRole.viewer))]
ProjEditor = Annotated[ProjectContext, Depends(require_project_role(ProjectRole.editor))]
DocViewer = Annotated[DocumentContext, Depends(require_document_role(ProjectRole.viewer))]
DocEditor = Annotated[DocumentContext, Depends(require_document_role(ProjectRole.editor))]
DocAdmin = Annotated[DocumentContext, Depends(require_document_role(ProjectRole.admin))]
VersionViewer = Annotated[VersionContext, Depends(require_version_access(ProjectRole.viewer))]
VersionEditor = Annotated[VersionContext, Depends(require_version_access(ProjectRole.editor))]


def _stream_blob(version: DocumentVersion) -> StreamingResponse:
    if version.processing_status == ProcessingStatus.quarantined:
        raise forbidden("Version unter Quarantaene — Download nicht erlaubt", code="quarantined")
    disposition = f"attachment; filename*=UTF-8''{quote(version.file_name)}"
    return StreamingResponse(
        get_storage().open_stream(version.storage_key),
        media_type=version.mime_type or "application/octet-stream",
        headers={"Content-Disposition": disposition},
    )


# ---- Projektgebundene Dokument-Liste / Upload ----


@router.get("/projects/{project_id}/documents", response_model=Page[DocumentListItem])
def list_documents(
    ctx: ProjViewer,
    session: SessionDep,
    limit: int = Query(default=50, le=100, ge=1),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None, pattern="^(active|archived|deleted)$"),
) -> Page[DocumentListItem]:
    # Papierkorb (status=deleted) nur fuer Projekt-Admin/Owner sichtbar, nicht fuer viewer/editor.
    if status == DocumentStatus.deleted and not role_satisfies(ctx.role, ProjectRole.admin):
        raise forbidden("Rolle fuer diese Aktion unzureichend")
    items, total = document_service.list_documents(
        session,
        project_id=ctx.project.id,
        limit=limit,
        offset=offset,
        search=search,
        status=status,
    )
    return Page(
        items=[DocumentListItem(**i) for i in items], total=total, limit=limit, offset=offset
    )


@router.post(
    "/projects/{project_id}/documents",
    response_model=DocumentDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_document(
    ctx: ProjEditor,
    session: SessionDep,
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=300),
    description: str | None = Form(default=None, max_length=4000),
    category: str | None = Form(default=None, max_length=100),
) -> DocumentDetailOut:
    document, version = document_service.create_document_with_version(
        session,
        project_id=ctx.project.id,
        title=title,
        description=description,
        category=category,
        upload=file,
        actor=ctx.user,
        ip=get_client_ip(request),
    )
    session.commit()
    session.refresh(document)
    session.refresh(version)
    enqueue_process_version(version.id)  # erst NACH dem Commit
    return build_detail(document, version)


# ---- Einzelnes Dokument ----


@router.get("/documents/{document_id}", response_model=DocumentDetailOut)
def get_document(ctx: DocViewer, session: SessionDep) -> DocumentDetailOut:
    current = document_service.get_current_version(session, ctx.document.id)
    return build_detail(ctx.document, current)


@router.patch("/documents/{document_id}", response_model=DocumentDetailOut)
def patch_document(
    body: DocumentMetadataPatch, ctx: DocEditor, session: SessionDep, request: Request
) -> DocumentDetailOut:
    document = document_service.update_metadata(
        session,
        document=ctx.document,
        title=body.title,
        description=body.description,
        category=body.category,
        status=body.status,
        actor=ctx.user,
        ip=get_client_ip(request),
    )
    session.commit()
    session.refresh(document)
    current = document_service.get_current_version(session, document.id)
    return build_detail(document, current)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(ctx: DocAdmin, session: SessionDep, request: Request) -> Response:
    compliance_service.soft_delete_document(
        session, document=ctx.document, actor=ctx.user, ip=get_client_ip(request)
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/documents/{document_id}/restore", response_model=DocumentDetailOut)
def restore_document(ctx: DocAdmin, session: SessionDep, request: Request) -> DocumentDetailOut:
    document = compliance_service.restore_document(
        session, document=ctx.document, actor=ctx.user, ip=get_client_ip(request)
    )
    session.commit()
    session.refresh(document)
    current = document_service.get_current_version(session, document.id)
    return build_detail(document, current)


@router.get("/documents/{document_id}/versions", response_model=list[VersionOut])
def get_versions(ctx: DocViewer, session: SessionDep) -> list[VersionOut]:
    return [
        VersionOut.model_validate(v)
        for v in document_service.list_versions(session, ctx.document.id)
    ]


@router.post(
    "/documents/{document_id}/versions",
    response_model=VersionOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_version(
    ctx: DocEditor,
    session: SessionDep,
    request: Request,
    file: UploadFile = File(...),
) -> VersionOut:
    version = document_service.add_version(
        session, document=ctx.document, upload=file, actor=ctx.user, ip=get_client_ip(request)
    )
    session.commit()
    session.refresh(version)
    enqueue_process_version(version.id)
    return VersionOut.model_validate(version)


# ---- Downloads (server-seitig autorisiert, keine oeffentlichen Pfade) ----


@router.get("/documents/{document_id}/download")
def download_current(ctx: DocViewer, session: SessionDep, request: Request) -> StreamingResponse:
    if ctx.document.status == DocumentStatus.deleted:
        raise not_found("Dokument nicht gefunden")
    current = document_service.get_current_version(session, ctx.document.id)
    if current is None:
        raise not_found("Keine Version vorhanden")
    write_audit_log(
        session,
        action=AuditAction.document_downloaded,
        entity_type="document_version",
        actor_user_id=ctx.user.id,
        entity_id=current.id,
        project_id=ctx.document.project_id,
        ip_address=get_client_ip(request),
        metadata={"version_number": current.version_number},
    )
    session.commit()
    return _stream_blob(current)


@router.post("/versions/{version_id}/reprocess", response_model=VersionOut)
def reprocess_version(ctx: VersionEditor, session: SessionDep, request: Request) -> VersionOut:
    version = document_service.reprocess_version(
        session,
        version=ctx.version,
        project_id=ctx.document.project_id,
        actor=ctx.user,
        ip=get_client_ip(request),
    )
    session.commit()
    session.refresh(version)
    enqueue_process_version(version.id)
    return VersionOut.model_validate(version)


@router.get("/versions/{version_id}/download")
def download_version(
    ctx: VersionViewer, session: SessionDep, request: Request
) -> StreamingResponse:
    if ctx.document.status == DocumentStatus.deleted:
        raise not_found("Dokument nicht gefunden")
    write_audit_log(
        session,
        action=AuditAction.document_downloaded,
        entity_type="document_version",
        actor_user_id=ctx.user.id,
        entity_id=ctx.version.id,
        project_id=ctx.document.project_id,
        ip_address=get_client_ip(request),
        metadata={"version_number": ctx.version.version_number},
    )
    session.commit()
    return _stream_blob(ctx.version)


def build_detail(document: Document, current: DocumentVersion | None) -> DocumentDetailOut:
    base = DocumentDetailOut.model_validate(document)
    if current is not None:
        base.current_version = VersionOut.model_validate(current)
    return base
