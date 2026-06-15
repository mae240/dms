"""Tests fuer Projekte, Mitgliedschaft und projektgebundene Zugriffskontrolle."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from dms_core.enums import AuditAction, ProjectRole
from dms_core.models.audit import AuditLog
from tests.factories import bearer, make_user


def _create_project(
    client: TestClient, owner_headers: dict[str, str], name: str = "Kunde A"
) -> str:
    res = client.post("/api/projects", json={"name": name}, headers=owner_headers)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["my_role"] == ProjectRole.owner
    return body["id"]


def test_create_and_list_project(client: TestClient, db_session: Session) -> None:
    owner = make_user(db_session, "owner@example.com")
    headers = bearer(owner)
    pid = _create_project(client, headers)

    listing = client.get("/api/projects", headers=headers)
    assert listing.status_code == 200
    data = listing.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == pid

    actions = set(db_session.exec(select(AuditLog.action)).all())
    assert AuditAction.project_created in actions


def test_non_member_cannot_access_project(client: TestClient, db_session: Session) -> None:
    owner = make_user(db_session, "owner2@example.com")
    outsider = make_user(db_session, "outsider@example.com")
    pid = _create_project(client, bearer(owner))

    # Nicht-Mitglied erhaelt 404 (Existenz wird nicht verraten).
    res = client.get(f"/api/projects/{pid}", headers=bearer(outsider))
    assert res.status_code == 404

    # ... und sieht das Projekt nicht in seiner Liste.
    listing = client.get("/api/projects", headers=bearer(outsider))
    assert listing.json()["total"] == 0


def test_add_member_by_email_and_role_enforcement(client: TestClient, db_session: Session) -> None:
    owner = make_user(db_session, "owner3@example.com")
    viewer_user = make_user(db_session, "viewer@example.com")
    pid = _create_project(client, bearer(owner))

    # Owner fuegt Viewer hinzu.
    add = client.post(
        f"/api/projects/{pid}/members",
        json={"email": "viewer@example.com", "role": "viewer"},
        headers=bearer(owner),
    )
    assert add.status_code == 201
    assert add.json()["role"] == "viewer"

    # Doppeltes Hinzufuegen -> 409.
    dup = client.post(
        f"/api/projects/{pid}/members",
        json={"email": "viewer@example.com", "role": "viewer"},
        headers=bearer(owner),
    )
    assert dup.status_code == 409

    # Unbekannte E-Mail -> 404.
    unknown = client.post(
        f"/api/projects/{pid}/members",
        json={"email": "ghost@example.com", "role": "viewer"},
        headers=bearer(owner),
    )
    assert unknown.status_code == 404

    # Viewer darf KEINE Mitglieder hinzufuegen (Rolle unzureichend -> 403).
    forbidden = client.post(
        f"/api/projects/{pid}/members",
        json={"email": "owner3@example.com", "role": "viewer"},
        headers=bearer(viewer_user),
    )
    assert forbidden.status_code == 403

    # Viewer darf das Projekt aber sehen.
    seen = client.get(f"/api/projects/{pid}", headers=bearer(viewer_user))
    assert seen.status_code == 200
    assert {m["email"] for m in seen.json()["members"]} == {
        "owner3@example.com",
        "viewer@example.com",
    }


def test_cannot_remove_owner_but_can_remove_member(client: TestClient, db_session: Session) -> None:
    owner = make_user(db_session, "owner4@example.com")
    member = make_user(db_session, "member4@example.com")
    pid = _create_project(client, bearer(owner))
    client.post(
        f"/api/projects/{pid}/members",
        json={"email": "member4@example.com", "role": "editor"},
        headers=bearer(owner),
    )

    # Owner-Mitgliedschaft ist geschuetzt.
    rm_owner = client.delete(f"/api/projects/{pid}/members/{owner.id}", headers=bearer(owner))
    assert rm_owner.status_code == 403

    # Normales Mitglied entfernen klappt.
    rm = client.delete(f"/api/projects/{pid}/members/{member.id}", headers=bearer(owner))
    assert rm.status_code == 204

    actions = set(db_session.exec(select(AuditLog.action)).all())
    assert AuditAction.project_member_added in actions
    assert AuditAction.project_member_removed in actions


def test_change_member_role(client: TestClient, db_session: Session) -> None:
    owner = make_user(db_session, "owner5@example.com")
    member = make_user(db_session, "member5@example.com")
    viewer = make_user(db_session, "viewer5@example.com")
    pid = _create_project(client, bearer(owner))
    for email, role in (("member5@example.com", "viewer"), ("viewer5@example.com", "viewer")):
        client.post(
            f"/api/projects/{pid}/members",
            json={"email": email, "role": role},
            headers=bearer(owner),
        )

    # Owner hebt Mitglied von viewer auf editor.
    up = client.patch(
        f"/api/projects/{pid}/members/{member.id}",
        json={"role": "editor"},
        headers=bearer(owner),
    )
    assert up.status_code == 200
    assert up.json()["role"] == "editor"

    # Owner-Rolle ist geschuetzt.
    protect = client.patch(
        f"/api/projects/{pid}/members/{owner.id}",
        json={"role": "admin"},
        headers=bearer(owner),
    )
    assert protect.status_code == 403

    # Niemanden zum Owner machen.
    to_owner = client.patch(
        f"/api/projects/{pid}/members/{member.id}",
        json={"role": "owner"},
        headers=bearer(owner),
    )
    assert to_owner.status_code == 403

    # Viewer darf keine Rollen aendern.
    forbidden = client.patch(
        f"/api/projects/{pid}/members/{member.id}",
        json={"role": "admin"},
        headers=bearer(viewer),
    )
    assert forbidden.status_code == 403

    assert AuditAction.project_member_role_changed in set(
        db_session.exec(select(AuditLog.action)).all()
    )


def test_update_and_archive_project(client: TestClient, db_session: Session) -> None:
    owner = make_user(db_session, "owner6@example.com")
    pid = _create_project(client, bearer(owner))

    upd = client.patch(
        f"/api/projects/{pid}",
        json={"name": "Kunde A (umbenannt)", "status": "archived"},
        headers=bearer(owner),
    )
    assert upd.status_code == 200
    assert upd.json()["name"] == "Kunde A (umbenannt)"
    assert upd.json()["status"] == "archived"

    # Aktiv-Liste enthaelt es nicht mehr, Archiv-Liste schon.
    active = client.get("/api/projects?status=active", headers=bearer(owner)).json()
    assert pid not in [p["id"] for p in active["items"]]
    archived = client.get("/api/projects?status=archived", headers=bearer(owner)).json()
    assert pid in [p["id"] for p in archived["items"]]


def test_soft_delete_and_restore_project(client: TestClient, db_session: Session) -> None:
    owner = make_user(db_session, "owner7@example.com")
    member_admin = make_user(db_session, "admin7@example.com")
    pid = _create_project(client, bearer(owner))
    client.post(
        f"/api/projects/{pid}/members",
        json={"email": "admin7@example.com", "role": "admin"},
        headers=bearer(owner),
    )

    # Nicht-Owner (admin) darf NICHT loeschen.
    assert client.delete(f"/api/projects/{pid}", headers=bearer(member_admin)).status_code == 403

    # Owner loescht (soft).
    assert client.delete(f"/api/projects/{pid}", headers=bearer(owner)).status_code == 204
    default_list = client.get("/api/projects", headers=bearer(owner)).json()
    assert pid not in [p["id"] for p in default_list["items"]]
    trash = client.get("/api/projects?status=deleted", headers=bearer(owner)).json()
    assert pid in [p["id"] for p in trash["items"]]

    # Wiederherstellen.
    restored = client.post(f"/api/projects/{pid}/restore", headers=bearer(owner))
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"

    actions = set(db_session.exec(select(AuditLog.action)).all())
    assert {AuditAction.project_deleted, AuditAction.project_restored} <= actions
