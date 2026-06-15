"""Einfaches Redis-basiertes Rate-Limiting (Fixed Window).

Schuetzt Auth-Endpunkte (/auth/login, /auth/refresh) gegen Brute-Force (Art. 32).
Bewusst minimal — kein verteiltes Token-Bucket noetig fuer ein MVP.
"""

from __future__ import annotations

import redis

from app.core.errors import ApiError
from dms_core.config import settings

_client: redis.Redis | None = None


def _redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def enforce_rate_limit(scope: str, identifier: str | None, *, limit: int, window_s: int = 60) -> None:
    """Erhoeht den Zaehler fuer (scope, identifier) und wirft 429 bei Ueberschreitung.

    Faellt bei Redis-Ausfall bewusst offen (fail-open), um Logins nicht komplett
    zu blockieren — Verfuegbarkeit vs. Brute-Force-Schutz im MVP abgewogen.

    Fehlt der identifier (z.B. keine Client-IP), wird fail-closed sofort 429
    geworfen — sonst landen alle anonymen Requests in einem Sammel-Key
    (DoS/Bypass). Das ist KEIN Redis-Ausfall, daher kein fail-open.
    """
    if not identifier:
        raise ApiError(
            429,
            "rate_limited",
            "Zu viele Versuche. Bitte spaeter erneut versuchen.",
        )
    key = f"rl:{scope}:{identifier}"
    try:
        client = _redis()
        # incr + expire atomar via Pipeline, sonst kann ein Key ohne TTL haengen
        # bleiben (Dauer-Block).
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_s, nx=True)
        current, _ = pipe.execute()
    except redis.RedisError:
        return  # fail-open
    if current > limit:
        raise ApiError(
            429,
            "rate_limited",
            "Zu viele Versuche. Bitte spaeter erneut versuchen.",
        )
