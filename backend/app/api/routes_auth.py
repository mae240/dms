"""Auth-Endpunkte: register-first-admin, login, refresh, logout."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, Response, status

from app.core.cookies import clear_refresh_cookie, set_refresh_cookie
from app.core.deps import CurrentUser, SessionDep, get_client_ip
from app.core.errors import ApiError, unauthorized
from app.core.ratelimit import enforce_rate_limit
from app.schemas.auth import ChangePasswordIn, LoginIn, RegisterFirstAdminIn, TokenOut
from app.services import auth_service
from dms_core.config import settings
from dms_core.security import AccessTokenError, decode_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(access: str) -> TokenOut:
    return TokenOut(access_token=access, expires_in=auth_service.access_ttl_seconds())


@router.post("/register-first-admin", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register_first_admin(
    body: RegisterFirstAdminIn, request: Request, response: Response, session: SessionDep
) -> TokenOut:
    ip = get_client_ip(request)
    # Argon2-DoS-Schutz: eigener, kleiner Bucket (Endpunkt wird im Normalfall
    # genau einmal aufgerufen).
    enforce_rate_limit("register", ip, limit=5)
    user, refresh = auth_service.register_first_admin(
        session, email=body.email, password=body.password, full_name=body.full_name, ip=ip
    )
    session.commit()
    set_refresh_cookie(response, refresh)
    return _token_response(auth_service.issue_access_token(user))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, response: Response, session: SessionDep) -> TokenOut:
    ip = get_client_ip(request)
    enforce_rate_limit("login", ip, limit=settings.auth_rate_limit_per_minute)
    try:
        user, refresh = auth_service.authenticate(
            session,
            email=body.email,
            password=body.password,
            ip=ip,
            user_agent=request.headers.get("user-agent"),
        )
    except ApiError:
        # Fehlversuch-Audit persistieren (authenticate() hat ihn geflusht),
        # danach den Fehler unveraendert weiterreichen.
        session.commit()
        raise
    session.commit()
    set_refresh_cookie(response, refresh)
    return _token_response(auth_service.issue_access_token(user))


@router.post("/refresh", response_model=TokenOut)
def refresh(request: Request, response: Response, session: SessionDep) -> TokenOut:
    ip = get_client_ip(request)
    enforce_rate_limit("refresh", ip, limit=settings.auth_rate_limit_per_minute)
    plain = request.cookies.get(settings.refresh_cookie_name)
    if not plain:
        raise unauthorized("Kein Refresh-Token", code="missing_refresh")
    user, new_refresh = auth_service.rotate_refresh(
        session, plain=plain, ip=ip, user_agent=request.headers.get("user-agent")
    )
    session.commit()
    set_refresh_cookie(response, new_refresh)
    return _token_response(auth_service.issue_access_token(user))


@router.post("/change-password", response_model=TokenOut)
def change_password(
    body: ChangePasswordIn,
    user: CurrentUser,
    request: Request,
    response: Response,
    session: SessionDep,
) -> TokenOut:
    ip = get_client_ip(request)
    enforce_rate_limit("change-password", ip, limit=5)
    refresh = auth_service.change_password(
        session,
        user=user,
        current_password=body.current_password,
        new_password=body.new_password,
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    session.commit()
    set_refresh_cookie(response, refresh)
    return _token_response(auth_service.issue_access_token(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, session: SessionDep) -> Response:
    ip = get_client_ip(request)
    plain = request.cookies.get(settings.refresh_cookie_name)

    # Best-effort: Actor aus dem (evtl. vorhandenen) Access-Token ableiten.
    actor_id = None
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        try:
            actor_id = uuid.UUID(str(decode_access_token(header[7:]).get("sub")))
        except (AccessTokenError, ValueError, TypeError):
            actor_id = None

    auth_service.logout(session, plain=plain, actor_user_id=actor_id, ip=ip)
    session.commit()
    clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
