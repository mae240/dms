"""Prod-Secret-/Sicherheits-Validierung der Settings (_enforce_prod_secrets)."""

from __future__ import annotations

import pytest

from dms_core.config import Settings

_SAFE_SECRET = "ein-starkes-zufaelliges-geheimnis-1234567890"
_SAFE_DB = "postgresql+psycopg://dms:starkes-prod-passwort@postgres:5432/dms"


def _prod(**overrides: object) -> Settings:
    base = {
        "environment": "production",
        "jwt_secret": _SAFE_SECRET,
        "database_url": _SAFE_DB,
        "refresh_cookie_secure": True,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_prod_rejects_insecure_jwt_secret() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET"):
        _prod(jwt_secret="dev-only-insecure-secret-change-me")


def test_prod_rejects_default_db_password() -> None:
    with pytest.raises(ValueError, match="DATABASE_URL"):
        _prod(database_url="postgresql+psycopg://dms:dms_dev_password_change_me@postgres:5432/dms")


def test_prod_requires_secure_refresh_cookie() -> None:
    with pytest.raises(ValueError, match="REFRESH_COOKIE_SECURE"):
        _prod(refresh_cookie_secure=False)


def test_prod_accepts_secure_config() -> None:
    settings = _prod()
    assert settings.environment == "production"
    assert settings.refresh_cookie_secure is True


def test_development_allows_insecure_defaults() -> None:
    # Im Dev-Betrieb sind die unsicheren Defaults bewusst erlaubt.
    settings = Settings(environment="development")
    assert settings.refresh_cookie_secure is False
