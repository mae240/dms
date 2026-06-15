"""Test-Hilfen: Benutzer anlegen und Bearer-Header erzeugen."""

from __future__ import annotations

import hashlib
import io
import uuid
from datetime import date, datetime

from sqlmodel import Session

from dms_core.enums import DocumentStatus, ProcessingStatus, ProjectRole
from dms_core.models.document import Document, DocumentVersion
from dms_core.models.project import Project, ProjectMember
from dms_core.models.user import User
from dms_core.security import create_access_token, hash_password
from dms_core.storage.base import StorageBackend

_DEFAULT_PW = "test-password-123"


def make_user(
    session: Session,
    email: str,
    *,
    full_name: str = "",
    superadmin: bool = False,
    active: bool = True,
    password: str = _DEFAULT_PW,
) -> User:
    user = User(
        email=email.strip().lower(),
        hashed_password=hash_password(password),
        full_name=full_name,
        is_active=active,
        is_superadmin=superadmin,
    )
    session.add(user)
    session.flush()
    return user


def bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def make_project(session: Session, owner: User, name: str = "Projekt") -> Project:
    project = Project(name=name, owner_id=owner.id)
    session.add(project)
    session.flush()
    session.add(ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectRole.owner))
    session.flush()
    return project


def make_document(
    session: Session,
    *,
    project_id: uuid.UUID,
    created_by: uuid.UUID,
    title: str = "Vertrag",
    status: str = DocumentStatus.active,
    legal_hold: bool = False,
    retention_until: date | None = None,
    deleted_at: datetime | None = None,
    purge_after: datetime | None = None,
) -> Document:
    doc = Document(
        project_id=project_id,
        title=title,
        created_by=created_by,
        status=status,
        legal_hold=legal_hold,
        retention_until=retention_until,
        deleted_at=deleted_at,
        purge_after=purge_after,
    )
    session.add(doc)
    session.flush()
    return doc


def make_version(
    session: Session,
    storage: StorageBackend,
    *,
    document_id: uuid.UUID,
    created_by: uuid.UUID,
    content: bytes = b"vertragsinhalt",
    version_number: int = 1,
) -> DocumentVersion:
    vid = uuid.uuid4()
    key = f"{document_id}/{vid}"
    storage.save(key, io.BytesIO(content))
    version = DocumentVersion(
        id=vid,
        document_id=document_id,
        version_number=version_number,
        file_name="vertrag.txt",
        file_hash=hashlib.sha256(content).hexdigest(),
        storage_key=key,
        mime_type="text/plain",
        size_bytes=len(content),
        processing_status=ProcessingStatus.ready,
        created_by=created_by,
    )
    session.add(version)
    session.flush()
    return version
