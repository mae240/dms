"""JWT-Access-Tokens (PyJWT) und Refresh-Token-Erzeugung.

Access-Token: kurzlebig, stateless, MINIMALE Claims (sub/exp/iat/jti) — KEINE
PII, da Tokens in Logs/Proxies landen koennen (Art. 5 Datenminimierung).
Refresh-Token: hoher Zufallswert, nur als Hash in der DB gespeichert; bei
Refresh wird der alte Token revoked (simple Rotation).
"""

from __future__ import annotations

import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from dms_core.config import settings


class AccessTokenError(Exception):
    """Ungueltiges, abgelaufenes oder manipuliertes Access-Token."""


def create_access_token(user_id: uuid.UUID | str, *, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_ttl_minutes)).timestamp()),
        "jti": secrets.token_urlsafe(8),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:  # abgelaufen, falsche Signatur, fehlerhaft
        raise AccessTokenError(str(exc)) from exc


def generate_refresh_token() -> str:
    """Erzeugt einen neuen, hochzufaelligen Refresh-Token (Klartext)."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """HMAC-SHA256 (mit jwt_secret) fuer die Speicherung — nie Klartext.

    HMAC statt blankem SHA-256: ohne Kenntnis des Secrets sind die DB-Hashes
    nicht offline angreifbar/vorberechenbar.
    """
    return hmac.new(settings.jwt_secret.encode(), token.encode(), "sha256").hexdigest()


def refresh_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days)
