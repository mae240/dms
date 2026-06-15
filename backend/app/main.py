"""FastAPI-Anwendung (Einstiegspunkt).

Single-Origin-Setup: im Normalfall liegt das Frontend hinter demselben Origin
(Reverse-Proxy /api, Dev: Vite-Proxy), sodass kein CORS noetig ist. Nur wenn
CORS_ORIGINS gesetzt ist, wird CORS mit explizitem Origin + credentials erlaubt.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import api_router
from app.core.errors import register_error_handlers
from dms_core.config import settings


def _add_security_headers(app: FastAPI) -> None:
    async def middleware(request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        return response

    app.add_middleware(BaseHTTPMiddleware, dispatch=middleware)


def create_app() -> FastAPI:
    app = FastAPI(
        title="DMS API",
        version="0.1.0",
        description="DSGVO-orientiertes Dokumentenmanagementsystem (MVP)",
    )

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    _add_security_headers(app)
    register_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
