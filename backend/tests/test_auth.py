"""Tests fuer Authentifizierung, Token-Rotation und Audit-Logging."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from dms_core.config import settings
from dms_core.enums import AuditAction
from dms_core.models.audit import AuditLog

ADMIN = {"email": "admin@example.com", "password": "supersecret123", "full_name": "Admin"}


def _register_admin(client: TestClient) -> str:
    res = client.post("/api/auth/register-first-admin", json=ADMIN)
    assert res.status_code == 201, res.text
    return res.json()["access_token"]


def test_register_first_admin_then_conflict(client: TestClient) -> None:
    token = _register_admin(client)
    assert token
    assert settings.refresh_cookie_name in client.cookies

    # Zweiter Aufruf muss abgelehnt werden (nur EIN erster Admin).
    res = client.post("/api/auth/register-first-admin", json=ADMIN)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "already_initialized"


def test_me_requires_auth(client: TestClient) -> None:
    token = _register_admin(client)

    res = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["email"] == ADMIN["email"]
    assert body["is_superadmin"] is True

    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer kaputt"}).status_code == 401


def test_login_success_and_wrong_password(client: TestClient, db_session: Session) -> None:
    _register_admin(client)
    client.cookies.clear()

    ok = client.post(
        "/api/auth/login", json={"email": ADMIN["email"], "password": ADMIN["password"]}
    )
    assert ok.status_code == 200
    assert ok.json()["access_token"]
    assert settings.refresh_cookie_name in client.cookies

    bad = client.post("/api/auth/login", json={"email": ADMIN["email"], "password": "falsch"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "invalid_credentials"

    actions = set(db_session.exec(select(AuditLog.action)).all())
    assert AuditAction.user_login in actions
    assert AuditAction.user_login_failed in actions


def test_unknown_user_is_generic_401(client: TestClient) -> None:
    _register_admin(client)
    res = client.post(
        "/api/auth/login", json={"email": "ghost@example.com", "password": "whatever1"}
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "invalid_credentials"


def test_refresh_rotates_and_old_token_is_rejected(client: TestClient) -> None:
    _register_admin(client)
    old_refresh = client.cookies.get(settings.refresh_cookie_name)
    assert old_refresh

    rotated = client.post("/api/auth/refresh")
    assert rotated.status_code == 200
    new_refresh = client.cookies.get(settings.refresh_cookie_name)
    assert new_refresh and new_refresh != old_refresh

    # Alter (rotierter) Refresh-Token darf nicht mehr funktionieren.
    reuse = client.post("/api/auth/refresh", cookies={settings.refresh_cookie_name: old_refresh})
    assert reuse.status_code == 401


def test_change_password(client: TestClient) -> None:
    token = _register_admin(client)
    auth = {"Authorization": f"Bearer {token}"}
    old_refresh = client.cookies.get(settings.refresh_cookie_name)

    # Falsches aktuelles Passwort -> 400.
    bad = client.post(
        "/api/auth/change-password",
        json={"current_password": "falsch", "new_password": "neuespasswort1"},
        headers=auth,
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "invalid_password"

    # Korrekt -> 200, neuer Access-Token.
    ok = client.post(
        "/api/auth/change-password",
        json={"current_password": ADMIN["password"], "new_password": "neuespasswort1"},
        headers=auth,
    )
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    # Alter Refresh-Token wurde widerrufen.
    reuse = client.post("/api/auth/refresh", cookies={settings.refresh_cookie_name: old_refresh})
    assert reuse.status_code == 401

    # Login mit neuem Passwort klappt, mit altem nicht.
    client.cookies.clear()
    assert (
        client.post(
            "/api/auth/login", json={"email": ADMIN["email"], "password": "neuespasswort1"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/auth/login", json={"email": ADMIN["email"], "password": ADMIN["password"]}
        ).status_code
        == 401
    )


def test_logout_clears_and_revokes(client: TestClient) -> None:
    token = _register_admin(client)
    refresh_before = client.cookies.get(settings.refresh_cookie_name)

    out = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert out.status_code == 204

    # Revoketer Token darf nicht mehr refreshen.
    res = client.post("/api/auth/refresh", cookies={settings.refresh_cookie_name: refresh_before})
    assert res.status_code == 401
