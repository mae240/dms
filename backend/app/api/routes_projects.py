"""Projekt-Endpunkte."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.deps import CurrentUser, SessionDep, get_client_ip
from app.core.project_access import ProjectContext, require_project_role
from app.schemas.common import Page
from app.schemas.project import (
    MemberAddIn,
    MemberOut,
    MemberRoleUpdate,
    ProjectCreate,
    ProjectDetailOut,
    ProjectOut,
    ProjectUpdate,
)
from app.schemas.retention import RetentionRuleDelete, RetentionRuleIn, RetentionRuleOut
from app.services import project_service
from dms_core.enums import ProjectRole

router = APIRouter(prefix="/projects", tags=["projects"])

ViewerCtx = Annotated[ProjectContext, Depends(require_project_role(ProjectRole.viewer))]
AdminCtx = Annotated[ProjectContext, Depends(require_project_role(ProjectRole.admin))]
OwnerCtx = Annotated[ProjectContext, Depends(require_project_role(ProjectRole.owner))]
OwnerCtxDeleted = Annotated[
    ProjectContext, Depends(require_project_role(ProjectRole.owner, allow_deleted=True))
]


@router.get("", response_model=Page[ProjectOut])
def list_projects(
    user: CurrentUser,
    session: SessionDep,
    limit: int = Query(default=50, le=100, ge=1),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None, pattern="^(active|archived|deleted)$"),
) -> Page[ProjectOut]:
    rows, total = project_service.list_my_projects(
        session, user=user, limit=limit, offset=offset, status=status
    )
    items = [ProjectOut.model_validate(p).model_copy(update={"my_role": role}) for p, role in rows]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    body: ProjectUpdate, ctx: AdminCtx, request: Request, session: SessionDep
) -> ProjectOut:
    project = project_service.update_project(
        session,
        project=ctx.project,
        name=body.name,
        description=body.description,
        status=body.status,
        actor=ctx.user,
        ip=get_client_ip(request),
    )
    session.commit()
    session.refresh(project)
    return ProjectOut.model_validate(project).model_copy(update={"my_role": ctx.role})


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(ctx: OwnerCtx, request: Request, session: SessionDep) -> Response:
    project_service.soft_delete_project(
        session, project=ctx.project, actor=ctx.user, ip=get_client_ip(request)
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{project_id}/restore", response_model=ProjectOut)
def restore_project(ctx: OwnerCtxDeleted, request: Request, session: SessionDep) -> ProjectOut:
    project = project_service.restore_project(
        session, project=ctx.project, actor=ctx.user, ip=get_client_ip(request)
    )
    session.commit()
    session.refresh(project)
    return ProjectOut.model_validate(project).model_copy(update={"my_role": ctx.role})


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate, user: CurrentUser, request: Request, session: SessionDep
) -> ProjectOut:
    project = project_service.create_project(
        session, owner=user, name=body.name, description=body.description, ip=get_client_ip(request)
    )
    session.commit()
    session.refresh(project)
    return ProjectOut.model_validate(project).model_copy(update={"my_role": ProjectRole.owner})


@router.get("/{project_id}", response_model=ProjectDetailOut)
def get_project(ctx: ViewerCtx, session: SessionDep) -> ProjectDetailOut:
    members = [
        MemberOut(
            user_id=m.user_id,
            email=u.email,
            full_name=u.full_name,
            role=m.role,
            created_at=m.created_at,
        )
        for m, u in project_service.list_members(session, project_id=ctx.project.id)
    ]
    base = ProjectOut.model_validate(ctx.project).model_copy(update={"my_role": ctx.role})
    return ProjectDetailOut(**base.model_dump(), members=members)


@router.post("/{project_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def add_member(
    body: MemberAddIn, ctx: AdminCtx, request: Request, session: SessionDep
) -> MemberOut:
    member, target = project_service.add_member(
        session,
        project_id=ctx.project.id,
        email=body.email,
        role=body.role,
        actor=ctx.user,
        ip=get_client_ip(request),
    )
    session.commit()
    return MemberOut(
        user_id=target.id,
        email=target.email,
        full_name=target.full_name,
        role=member.role,
        created_at=member.created_at,
    )


@router.patch("/{project_id}/members/{user_id}", response_model=MemberOut)
def change_member_role(
    user_id: uuid.UUID,
    body: MemberRoleUpdate,
    ctx: AdminCtx,
    request: Request,
    session: SessionDep,
) -> MemberOut:
    member, target = project_service.change_member_role(
        session,
        project_id=ctx.project.id,
        target_user_id=user_id,
        role=body.role,
        actor=ctx.user,
        ip=get_client_ip(request),
    )
    session.commit()
    return MemberOut(
        user_id=target.id,
        email=target.email,
        full_name=target.full_name,
        role=member.role,
        created_at=member.created_at,
    )


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    user_id: uuid.UUID, ctx: AdminCtx, request: Request, session: SessionDep
) -> Response:
    project_service.remove_member(
        session,
        project_id=ctx.project.id,
        target_user_id=user_id,
        actor=ctx.user,
        ip=get_client_ip(request),
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{project_id}/retention-rules", response_model=RetentionRuleOut)
def put_retention_rule(
    body: RetentionRuleIn, ctx: AdminCtx, request: Request, session: SessionDep
) -> RetentionRuleOut:
    rule = project_service.upsert_retention_rule(
        session,
        project=ctx.project,
        category=body.category,
        max_days=body.max_days,
        actor=ctx.user,
        ip=get_client_ip(request),
    )
    session.commit()
    session.refresh(rule)
    return RetentionRuleOut.model_validate(rule)


@router.get("/{project_id}/retention-rules", response_model=list[RetentionRuleOut])
def get_retention_rules(ctx: AdminCtx, session: SessionDep) -> list[RetentionRuleOut]:
    return [
        RetentionRuleOut.model_validate(r)
        for r in project_service.list_retention_rules(session, project=ctx.project)
    ]


@router.delete("/{project_id}/retention-rules", status_code=status.HTTP_204_NO_CONTENT)
def delete_retention_rule(
    body: RetentionRuleDelete, ctx: AdminCtx, request: Request, session: SessionDep
) -> Response:
    project_service.delete_retention_rule(
        session,
        project=ctx.project,
        category=body.category,
        actor=ctx.user,
        ip=get_client_ip(request),
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
