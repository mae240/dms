"""Authentifizierungs-Geschaeftslogik (inkl. Audit-Logging).

Token-Strategie:
- Access-Token: kurzlebig, stateless (JWT).
- Refresh-Token: hochzufaellig, nur als Hash in der DB; bei Refresh wird der
  alte Token revoked (simple Rotation). Reuse-Detection/Family ist post-MVP.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.core.errors import bad_request, conflict, unauthorized
from dms_core.audit import write_audit_log
from dms_core.config import settings
from dms_core.enums import AuditAction
from dms_core.models.user import RefreshToken, User
from dms_core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    verify_password,
)
from dms_core.security.tokens import refresh_expiry


def _issue_refresh_token(
    session: Session, user: User, *, ip: str | None, user_agent: str | None
) -> str:
    plain = generate_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(plain),
            expires_at=refresh_expiry(),
            ip_address=ip,
            user_agent=user_agent,
        )
    )
    return plain


def issue_access_token(user: User) -> str:
    return create_access_token(user.id)


def access_ttl_seconds() -> int:
    return settings.access_token_ttl_minutes * 60


def register_first_admin(
    session: Session, *, email: str, password: str, full_name: str, ip: str | None
) -> tuple[User, str]:
    """Legt den ersten Admin an — nur moeglich, solange kein User existiert."""
    existing = session.exec(select(User.id).limit(1)).first()
    if existing is not None:
        raise conflict("Es existiert bereits ein Benutzer.", code="already_initialized")

    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        is_active=True,
        is_superadmin=True,
    )
    session.add(user)
    session.flush()

    refresh = _issue_refresh_token(session, user, ip=ip, user_agent=None)
    write_audit_log(
        session,
        action=AuditAction.user_login,
        entity_type="user",
        actor_user_id=user.id,
        entity_id=user.id,
        ip_address=ip,
        metadata={"event": "first_admin_registered"},
    )
    return user, refresh


def authenticate(
    session: Session, *, email: str, password: str, ip: str | None, user_agent: str | None
) -> tuple[User, str]:
    user = session.exec(select(User).where(User.email == email)).first()

    # Generische Fehlermeldung gegen User-Enumeration (Art. 32).
    if user is None or not user.is_active or not verify_password(password, user.hashed_password):
        write_audit_log(
            session,
            action=AuditAction.user_login_failed,
            entity_type="user",
            actor_user_id=user.id if user else None,
            ip_address=ip,
            # Kein Klartext: Mail wird nie geschwaerzt. Hash erlaubt Korrelation
            # ohne PII (Datenminimierung Art. 5).
            metadata={"email_sha256": hashlib.sha256(email.lower().encode()).hexdigest()},
        )
        session.commit()  # Audit-Eintrag des Fehlversuchs persistieren
        raise unauthorized("Ungueltige Zugangsdaten", code="invalid_credentials")

    # Passwort-Hash bei Bedarf auf aktuelle Parameter heben.
    if needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(password)
        session.add(user)

    refresh = _issue_refresh_token(session, user, ip=ip, user_agent=user_agent)
    write_audit_log(
        session,
        action=AuditAction.user_login,
        entity_type="user",
        actor_user_id=user.id,
        entity_id=user.id,
        ip_address=ip,
    )
    return user, refresh


def _lookup_valid_refresh(session: Session, plain: str) -> RefreshToken:
    token = session.exec(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(plain))
    ).first()
    if token is None or token.revoked_at is not None:
        raise unauthorized("Refresh-Token ungueltig", code="invalid_refresh")
    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        raise unauthorized("Refresh-Token abgelaufen", code="expired_refresh")
    return token


def rotate_refresh(
    session: Session, *, plain: str, ip: str | None, user_agent: str | None
) -> tuple[User, str]:
    token = _lookup_valid_refresh(session, plain)
    user = session.get(User, token.user_id)
    if user is None or not user.is_active:
        raise unauthorized("Konto nicht aktiv", code="inactive_account")

    # Simple Rotation: alten Token revoken, neuen ausgeben.
    token.revoked_at = datetime.now(UTC)
    session.add(token)
    new_refresh = _issue_refresh_token(session, user, ip=ip, user_agent=user_agent)
    return user, new_refresh


def change_password(
    session: Session,
    *,
    user: User,
    current_password: str,
    new_password: str,
    ip: str | None,
    user_agent: str | None,
) -> str:
    """Aendert das Passwort, widerruft ALLE bestehenden Refresh-Tokens (andere
    Sitzungen werden abgemeldet) und gibt einen frischen Refresh-Token fuer die
    aktuelle Sitzung zurueck."""
    if not verify_password(current_password, user.hashed_password):
        raise bad_request("Aktuelles Passwort ist falsch", code="invalid_password")

    user.hashed_password = hash_password(new_password)
    session.add(user)

    now = datetime.now(UTC)
    for token in session.exec(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
        )
    ).all():
        token.revoked_at = now
        session.add(token)

    new_refresh = _issue_refresh_token(session, user, ip=ip, user_agent=user_agent)
    write_audit_log(
        session,
        action=AuditAction.user_password_changed,
        entity_type="user",
        actor_user_id=user.id,
        entity_id=user.id,
        ip_address=ip,
    )
    return new_refresh


def logout(
    session: Session, *, plain: str | None, actor_user_id: uuid.UUID | None, ip: str | None
) -> None:
    if plain:
        token = session.exec(
            select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(plain))
        ).first()
        if token is not None and token.revoked_at is None:
            token.revoked_at = datetime.now(UTC)
            session.add(token)
    if actor_user_id is not None:
        write_audit_log(
            session,
            action=AuditAction.user_logout,
            entity_type="user",
            actor_user_id=actor_user_id,
            entity_id=actor_user_id,
            ip_address=ip,
        )
