"""Projekt- und Mitgliedschafts-Geschaeftslogik (inkl. Audit)."""

from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlmodel import Session, select

from datetime import UTC, datetime

from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.project_access import get_membership
from dms_core.audit import write_audit_log
from dms_core.enums import AuditAction, ProjectRole, ProjectStatus
from dms_core.models.project import Project, ProjectMember
from dms_core.models.user import User


def create_project(
    session: Session, *, owner: User, name: str, description: str | None, ip: str | None
) -> Project:
    project = Project(name=name, description=description, owner_id=owner.id)
    session.add(project)
    session.flush()

    # Ersteller wird Owner-Mitglied:
    session.add(ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectRole.owner))
    write_audit_log(
        session,
        action=AuditAction.project_created,
        entity_type="project",
        actor_user_id=owner.id,
        entity_id=project.id,
        project_id=project.id,
        ip_address=ip,
        metadata={"name": name},
    )
    return project


def list_my_projects(
    session: Session, *, user: User, limit: int, offset: int, status: str | None = None
) -> tuple[list[tuple[Project, str]], int]:
    conditions = [ProjectMember.user_id == user.id]
    if status:
        conditions.append(Project.status == status)
    else:
        conditions.append(Project.status != ProjectStatus.deleted)

    base = (
        select(Project, ProjectMember.role)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(*conditions)
    )
    total = session.exec(
        select(func.count())
        .select_from(ProjectMember)
        .join(Project, Project.id == ProjectMember.project_id)
        .where(*conditions)
    ).one()
    rows = session.exec(
        base.order_by(Project.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return [(p, role) for p, role in rows], total


def update_project(
    session: Session,
    *,
    project: Project,
    name: str | None,
    description: str | None,
    status: str | None,
    actor: User,
    ip: str | None,
) -> Project:
    changed: dict[str, object] = {}
    if name is not None:
        project.name = name
        changed["name"] = name
    if description is not None:
        project.description = description
        changed["description"] = True
    if status is not None:
        # Ueber diesen Weg nur active/archived; Loeschung laeuft ueber DELETE.
        if status not in (ProjectStatus.active, ProjectStatus.archived):
            raise bad_request("Ungueltiger Status", code="invalid_status")
        project.status = status
        project.deleted_at = None
        changed["status"] = status

    session.add(project)
    write_audit_log(
        session,
        action=AuditAction.project_updated,
        entity_type="project",
        actor_user_id=actor.id,
        entity_id=project.id,
        project_id=project.id,
        ip_address=ip,
        metadata={"fields": list(changed.keys())},
    )
    return project


def soft_delete_project(
    session: Session, *, project: Project, actor: User, ip: str | None
) -> Project:
    if project.status == ProjectStatus.deleted:
        raise bad_request("Projekt ist bereits geloescht", code="already_deleted")
    project.status = ProjectStatus.deleted
    project.deleted_at = datetime.now(UTC)
    session.add(project)
    write_audit_log(
        session,
        action=AuditAction.project_deleted,
        entity_type="project",
        actor_user_id=actor.id,
        entity_id=project.id,
        project_id=project.id,
        ip_address=ip,
    )
    return project


def restore_project(
    session: Session, *, project: Project, actor: User, ip: str | None
) -> Project:
    if project.status != ProjectStatus.deleted:
        raise bad_request("Nur geloeschte Projekte koennen wiederhergestellt werden",
                          code="not_deleted")
    project.status = ProjectStatus.active
    project.deleted_at = None
    session.add(project)
    write_audit_log(
        session,
        action=AuditAction.project_restored,
        entity_type="project",
        actor_user_id=actor.id,
        entity_id=project.id,
        project_id=project.id,
        ip_address=ip,
    )
    return project


def list_members(session: Session, *, project_id: uuid.UUID) -> list[tuple[ProjectMember, User]]:
    rows = session.exec(
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.created_at.asc())
    ).all()
    return list(rows)


def add_member(
    session: Session,
    *,
    project_id: uuid.UUID,
    email: str,
    role: ProjectRole,
    actor: User,
    ip: str | None,
) -> tuple[ProjectMember, User]:
    target = session.exec(select(User).where(User.email == email)).first()
    if target is None or not target.is_active:
        raise not_found("Benutzer nicht gefunden", code="user_not_found")

    if get_membership(session, project_id, target.id) is not None:
        raise conflict("Benutzer ist bereits Mitglied", code="already_member")

    member = ProjectMember(project_id=project_id, user_id=target.id, role=role)
    session.add(member)
    write_audit_log(
        session,
        action=AuditAction.project_member_added,
        entity_type="project_member",
        actor_user_id=actor.id,
        entity_id=target.id,
        project_id=project_id,
        ip_address=ip,
        metadata={"role": role.value, "member_email": email},
    )
    return member, target


def change_member_role(
    session: Session,
    *,
    project_id: uuid.UUID,
    target_user_id: uuid.UUID,
    role: ProjectRole,
    actor: User,
    ip: str | None,
) -> tuple[ProjectMember, User]:
    membership = get_membership(session, project_id, target_user_id)
    if membership is None:
        raise not_found("Mitglied nicht gefunden", code="member_not_found")
    if membership.role == ProjectRole.owner or role == ProjectRole.owner:
        # Der Owner ist geschuetzt und kann nicht (um)gesetzt werden.
        raise forbidden("Die Owner-Rolle kann nicht geaendert werden", code="owner_protected")

    membership.role = role
    session.add(membership)
    target = session.get(User, target_user_id)
    write_audit_log(
        session,
        action=AuditAction.project_member_role_changed,
        entity_type="project_member",
        actor_user_id=actor.id,
        entity_id=target_user_id,
        project_id=project_id,
        ip_address=ip,
        metadata={"role": role.value},
    )
    return membership, target  # type: ignore[return-value]


def remove_member(
    session: Session,
    *,
    project_id: uuid.UUID,
    target_user_id: uuid.UUID,
    actor: User,
    ip: str | None,
) -> None:
    membership = get_membership(session, project_id, target_user_id)
    if membership is None:
        raise not_found("Mitglied nicht gefunden", code="member_not_found")
    if membership.role == ProjectRole.owner:
        raise forbidden("Der Projekt-Owner kann nicht entfernt werden", code="cannot_remove_owner")

    session.delete(membership)
    write_audit_log(
        session,
        action=AuditAction.project_member_removed,
        entity_type="project_member",
        actor_user_id=actor.id,
        entity_id=target_user_id,
        project_id=project_id,
        ip_address=ip,
    )
