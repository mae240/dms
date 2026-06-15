"""Wiederverwendbare FastAPI-Dependencies.

Zentrale Stelle fuer Authentifizierung und Zugriffskontrolle. Default = KEIN
Zugriff (Art. 25): Endpunkte muessen explizit eine Dependency anfordern.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Request
from sqlmodel import Session

from app.core.errors import forbidden, unauthorized
from dms_core.config import settings
from dms_core.db import get_session
from dms_core.models.user import User
from dms_core.security import AccessTokenError, decode_access_token

SessionDep = Annotated[Session, Depends(get_session)]


def get_client_ip(request: Request) -> str | None:
    """Client-IP fuer Rate-Limiting/Audit.

    X-Forwarded-For wird NUR ausgewertet wenn settings.trust_proxy_headers True
    ist — sonst ist die Spoofing-Gefahr (Rate-Limit-Bypass) zu gross. Hinter
    einem Reverse-Proxy: trust_proxy_headers=true setzen UND uvicorn mit
    --proxy-headers --forwarded-allow-ips=<proxy> betreiben.
    """
    if settings.trust_proxy_headers:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise unauthorized("Kein gueltiges Bearer-Token")
    return token


def get_current_user(request: Request, session: SessionDep) -> User:
    token = _bearer_token(request)
    try:
        payload = decode_access_token(token)
    except AccessTokenError as exc:
        raise unauthorized("Token ungueltig oder abgelaufen") from exc

    sub = payload.get("sub")
    try:
        user_id = uuid.UUID(str(sub))
    except (ValueError, TypeError) as exc:
        raise unauthorized("Token-Subject ungueltig") from exc

    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized("Konto nicht gefunden oder deaktiviert")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_superadmin(user: CurrentUser) -> User:
    """Fuer systemweite Compliance-Endpunkte (Audit lesen, Export ausloesen)."""
    if not user.is_superadmin:
        raise forbidden("Erfordert Superadmin-Rechte")
    return user


SuperadminDep = Annotated[User, Depends(require_superadmin)]
