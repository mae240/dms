"""Zentrale Konfiguration via pydantic-settings.

Alle Secrets/Tunables kommen aus der Umgebung (.env). In Produktion failt
die Konfiguration hart, wenn unsichere Default-Secrets verwendet werden.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_SECRETS = {"dev-only-insecure-secret-change-me", "", "change-me"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    environment: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"

    # Datenbank
    database_url: str = "postgresql+psycopg://dms:dms_dev_password_change_me@postgres:5432/dms"
    # Connection-Pool — auf die FastAPI-Threadpool-Groesse (40) abstimmen.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30

    # Redis / Celery
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_visibility_timeout: int = 7200

    # Auth / JWT
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    refresh_cookie_name: str = "dms_refresh"
    refresh_cookie_secure: bool = False
    refresh_cookie_samesite: Literal["strict", "lax", "none"] = "strict"

    # Storage (SFTP noch nicht implementiert — Literal bewusst auf 'local' begrenzt)
    storage_backend: Literal["local"] = "local"
    storage_root: str = "/data/storage"
    export_root: str = "/data/exports"

    # Upload / Validierung
    max_upload_bytes: int = 50 * 1024 * 1024
    allowed_mime_types: str = (
        "application/pdf,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "text/plain,image/png,image/jpeg"
    )

    # Retention / Compliance
    default_retention_days: int = 365
    purge_grace_days: int = 30
    export_ttl_hours: int = 24
    audit_ip_retention_days: int = 90

    # Rate Limiting
    auth_rate_limit_per_minute: int = 10
    # Proxy: X-Forwarded-For NUR vertrauen wenn hinter einem Reverse-Proxy. Dann
    # zusaetzlich uvicorn mit --proxy-headers --forwarded-allow-ips=<proxy> betreiben.
    trust_proxy_headers: bool = False

    # CORS (bei Single-Origin leer lassen)
    cors_origins: str = ""

    @property
    def allowed_mime_set(self) -> set[str]:
        return {m.strip() for m in self.allowed_mime_types.split(",") if m.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("log_level")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def _enforce_prod_secrets(self) -> Settings:
        if self.environment == "production" and self.jwt_secret in _INSECURE_SECRETS:
            raise ValueError(
                "JWT_SECRET ist in Produktion nicht gesetzt oder unsicher. "
                "Bitte ein starkes Geheimnis in der Umgebung setzen."
            )
        if self.environment == "production" and "dms_dev_password_change_me" in self.database_url:
            raise ValueError(
                "DATABASE_URL nutzt in Produktion das unsichere Default-Passwort. "
                "Bitte ein starkes DB-Passwort in der Umgebung setzen."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
