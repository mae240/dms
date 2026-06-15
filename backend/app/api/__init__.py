"""API-Router-Aggregation. Alle Routen liegen unter dem Prefix /api."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes_admin import router as admin_router
from app.api.routes_auth import router as auth_router
from app.api.routes_documents import router as documents_router
from app.api.routes_health import router as health_router
from app.api.routes_me import router as me_router
from app.api.routes_projects import router as projects_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(me_router)
api_router.include_router(projects_router)
api_router.include_router(documents_router)
api_router.include_router(admin_router)
