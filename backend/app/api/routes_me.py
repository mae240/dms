"""Aktueller Benutzer: GET /me, GET /me/recent-documents."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, SessionDep
from app.schemas.auth import UserOut
from app.schemas.document import RecentDocumentOut
from app.services import document_service

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/me/recent-documents", response_model=list[RecentDocumentOut])
def recent_documents(
    user: CurrentUser,
    session: SessionDep,
    limit: int = Query(default=10, le=50, ge=1),
) -> list[RecentDocumentOut]:
    items = document_service.recent_documents(session, user=user, limit=limit)
    return [RecentDocumentOut(**i) for i in items]
