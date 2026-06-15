"""Projektgebundene Zugriffskontrolle (Privacy by Default, Art. 25).

require_project_role(min_role) liefert eine FastAPI-Dependency, die:
1. das Projekt anhand des Pfad-Parameters project_id laedt,
2. die Mitgliedschaft des aktuellen Users prueft (Nicht-Mitglieder erhalten 404,
   um die Existenz nicht zu verraten — IDOR-Schutz),
3. die Rolle gegen min_role prueft.

WICHTIG: Superadmin umgeht die Projekt-Mitgliedschaft NICHT. Systemweite Rechte
gelten nur fuer Compliance-Endpunkte (/admin/*), nicht fuer Projekt-/Dokument-
Zugriff — so bleibt die Projekt-Isolation strikt.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlmodel import Session, select

from app.core.deps import CurrentUser, SessionDep
from app.core.errors import forbidden, not_found
from dms_core.enums import role_satisfies
from dms_core.models.document import Document, DocumentVersion
from dms_core.models.project import Project, ProjectMember
from dms_core.models.user import User


@dataclass
class ProjectContext:
    project: Project
    user: User
    role: str


@dataclass
class DocumentContext:
    document: Document
    user: User
    role: str


@dataclass
class VersionContext:
    version: DocumentVersion
    document: Document
    user: User
    role: str


def require_project_role(
    min_role: str, *, allow_deleted: bool = False
) -> Callable[..., ProjectContext]:
    def dependency(project_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> ProjectContext:
        project = session.get(Project, project_id)
        if project is None or (project.deleted_at is not None and not allow_deleted):
            raise not_found("Projekt nicht gefunden")

        membership = session.exec(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user.id,
            )
        ).first()
        if membership is None:
            raise not_found("Projekt nicht gefunden")  # Existenz nicht verraten
        if not role_satisfies(membership.role, min_role):
            raise forbidden("Rolle fuer diese Aktion unzureichend")
        return ProjectContext(project=project, user=user, role=membership.role)

    return dependency


def get_membership(
    session: Session, project_id: uuid.UUID, user_id: uuid.UUID
) -> ProjectMember | None:
    return session.exec(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    ).first()


def require_document_role(min_role: str) -> Callable[..., DocumentContext]:
    def dependency(
        document_id: uuid.UUID, user: CurrentUser, session: SessionDep
    ) -> DocumentContext:
        document = session.get(Document, document_id)
        if document is None:
            raise not_found("Dokument nicht gefunden")
        membership = get_membership(session, document.project_id, user.id)
        if membership is None:
            raise not_found("Dokument nicht gefunden")  # Existenz nicht verraten
        if not role_satisfies(membership.role, min_role):
            raise forbidden("Rolle fuer diese Aktion unzureichend")
        return DocumentContext(document=document, user=user, role=membership.role)

    return dependency


def require_version_access(min_role: str) -> Callable[..., VersionContext]:
    def dependency(version_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> VersionContext:
        version = session.get(DocumentVersion, version_id)
        if version is None:
            raise not_found("Version nicht gefunden")
        document = session.get(Document, version.document_id)
        if document is None:
            raise not_found("Version nicht gefunden")
        membership = get_membership(session, document.project_id, user.id)
        if membership is None:
            raise not_found("Version nicht gefunden")
        if not role_satisfies(membership.role, min_role):
            raise forbidden("Rolle fuer diese Aktion unzureichend")
        return VersionContext(version=version, document=document, user=user, role=membership.role)

    return dependency
