"""Prod-Secret-/Sicherheits-Validierung der Settings (_enforce_prod_secrets)."""

from __future__ import annotations

import base64

import pytest

from dms_core.config import Settings

_SAFE_SECRET = "ein-starkes-zufaelliges-geheimnis-1234567890"
_SAFE_DB = "postgresql+psycopg://dms:starkes-prod-passwort@postgres:5432/dms"
_SAFE_KEY = base64.b64encode(b"\x07" * 32).decode()


def _prod(**overrides: object) -> Settings:
    base = {
        "environment": "production",
        "jwt_secret": _SAFE_SECRET,
        "database_url": _SAFE_DB,
        "refresh_cookie_secure": True,
        "storage_encryption_keys": f"1:{_SAFE_KEY}",
        "storage_active_key_id": 1,
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


def test_prod_requires_storage_keyring() -> None:
    with pytest.raises(ValueError, match="STORAGE_ENCRYPTION_KEYS"):
        _prod(storage_encryption_keys="", storage_active_key_id=0)


def test_prod_requires_active_key_in_ring() -> None:
    key = base64.b64encode(b"\x00" * 32).decode()
    with pytest.raises(ValueError, match="STORAGE_ACTIVE_KEY_ID"):
        _prod(storage_encryption_keys=f"1:{key}", storage_active_key_id=9)


def test_keyring_parses() -> None:
    k1 = base64.b64encode(b"\x01" * 32).decode()
    k2 = base64.b64encode(b"\x02" * 32).decode()
    s = Settings(storage_encryption_keys=f"1:{k1},2:{k2}", storage_active_key_id=2)
    ring = s.storage_keyring
    assert set(ring) == {1, 2}
    assert ring[2] == b"\x02" * 32
