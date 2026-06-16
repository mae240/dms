"""Tests fuer DSGVO-/Compliance-Funktionen."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from dms_core import maintenance
from dms_core.enums import AuditAction, DocumentStatus, ExportStatus
from dms_core.models.audit import AuditLog
from dms_core.models.document import Document
from dms_core.models.export import UserExport
from dms_core.models.project import ProjectMember, RetentionRule
from dms_core.models.user import RefreshToken
from tests.factories import bearer, make_document, make_project, make_user, make_version

PAST = datetime(2020, 1, 1, tzinfo=UTC)
FUTURE_DATE = date(2999, 1, 1)


def _project_with_document(db_session, *, age_days, category=None):  # noqa: ANN001, ANN202
    """Legt Projekt + aktives Dokument an, dessen created_at age_days zurueckliegt."""
    owner = make_user(db_session, f"ret-{datetime.now(UTC).timestamp()}@ex.com")
    project = make_project(db_session, owner)
    doc = make_document(db_session, project_id=project.id, created_by=owner.id)
    # created_at/category werden nach make_document(...) am Objekt gesetzt, da die
    # Factory diese Felder nicht als Parameter akzeptiert.
    doc.created_at = datetime.now(UTC) - timedelta(days=age_days)
    doc.category = category
    db_session.add(doc)
    db_session.flush()
    return project, doc


def _rule(session, project, category, max_days):  # noqa: ANN001, ANN202
    r = RetentionRule(project_id=project.id, category=category, max_days=max_days)
    session.add(r)
    session.flush()
    return r


def test_auto_expire_off_when_no_rule(db_session):  # noqa: ANN001
    _, doc = _project_with_document(db_session, age_days=10_000)
    assert maintenance.auto_soft_delete_expired(db_session) == 0
    db_session.refresh(doc)
    assert doc.status == "active"


def test_auto_expire_project_default(db_session):  # noqa: ANN001
    project, doc = _project_with_document(db_session, age_days=400)
    doc.retention_until = None
    db_session.add(doc)
    _rule(db_session, project, None, 365)  # Projekt-Default
    assert maintenance.auto_soft_delete_expired(db_session) == 1
    db_session.refresh(doc)
    assert doc.status == "deleted" and doc.purge_after is not None


def test_category_rule_overrides_default(db_session):  # noqa: ANN001
    project, doc = _project_with_document(db_session, age_days=400, category="Rechnung")
    doc.retention_until = None
    db_session.add(doc)
    _rule(db_session, project, None, 365)  # Default: loeschen nach 365
    _rule(db_session, project, "Rechnung", None)  # aber Rechnung = exempt
    assert maintenance.auto_soft_delete_expired(db_session) == 0
    db_session.refresh(doc)
    assert doc.status == "active"


def test_category_rule_shorter_than_default(db_session):  # noqa: ANN001
    project, doc = _project_with_document(db_session, age_days=40, category="Entwurf")
    doc.retention_until = None
    db_session.add(doc)
    _rule(db_session, project, "Entwurf", 30)  # Entwurf schon nach 30 Tagen weg
    assert maintenance.auto_soft_delete_expired(db_session) == 1


def test_auto_expire_respects_legal_hold_and_min_retention(db_session):  # noqa: ANN001
    project, doc = _project_with_document(db_session, age_days=400)
    _rule(db_session, project, None, 365)
    doc.legal_hold = True
    db_session.add(doc)
    assert maintenance.auto_soft_delete_expired(db_session) == 0
    doc.legal_hold = False
    doc.retention_until = date.today() + timedelta(days=30)  # Mindest-Aufbewahrung laeuft noch
    db_session.add(doc)
    assert maintenance.auto_soft_delete_expired(db_session) == 0


# ---------- Soft-Delete / Restore (API) ----------


def test_delete_only_soft_deletes_and_restore(client: TestClient, db_session: Session) -> None:
    owner = make_user(db_session, "o@ex.com")
    project = make_project(db_session, owner)
    doc = make_document(db_session, project_id=project.id, created_by=owner.id)

    res = client.delete(f"/api/documents/{doc.id}", headers=bearer(owner))
    assert res.status_code == 204

    db_session.expire_all()
    stored = db_session.get(Document, doc.id)
    assert stored is not None  # nur Soft-Delete
    assert stored.status == DocumentStatus.deleted
    assert stored.deleted_at is not None
    assert stored.purge_after is not None

    restored = client.post(f"/api/documents/{doc.id}/restore", headers=bearer(owner))
    assert restored.status_code == 200
    db_session.expire_all()
    stored = db_session.get(Document, doc.id)
    assert stored.status == DocumentStatus.active
    assert stored.purge_after is None  # WICHTIG fuer Restore


def test_legal_hold_blocks_soft_delete(client: TestClient, db_session: Session) -> None:
    owner = make_user(db_session, "o2@ex.com")
    admin = make_user(db_session, "super@ex.com", superadmin=True)
    project = make_project(db_session, owner)
    doc = make_document(db_session, project_id=project.id, created_by=owner.id)

    hold = client.post(
        f"/api/admin/documents/{doc.id}/legal-hold",
        json={"legal_hold": True},
        headers=bearer(admin),
    )
    assert hold.status_code == 200

    res = client.delete(f"/api/documents/{doc.id}", headers=bearer(owner))
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "legal_hold"


# ---------- Purge (Kernlogik, kritisch) ----------


def test_legal_hold_blocks_purge(db_session: Session, tmp_storage) -> None:  # noqa: ANN001
    owner = make_user(db_session, "p1@ex.com")
    project = make_project(db_session, owner)
    doc = make_document(
        db_session,
        project_id=project.id,
        created_by=owner.id,
        status=DocumentStatus.deleted,
        deleted_at=PAST,
        purge_after=PAST,
        legal_hold=True,
    )
    version = make_version(db_session, tmp_storage, document_id=doc.id, created_by=owner.id)
    blob_key = version.storage_key  # vor dem Purge festhalten (Zeile wird geloescht)

    # Legal Hold -> Purge laesst das Dokument unangetastet.
    assert maintenance.purge_deleted_documents(db_session, tmp_storage) == 0
    assert db_session.get(Document, doc.id) is not None
    assert tmp_storage.exists(blob_key)

    # Legal Hold entfernt -> Purge loescht Zeilen UND Blob, schreibt Audit.
    doc.legal_hold = False
    db_session.add(doc)
    db_session.flush()
    assert maintenance.purge_deleted_documents(db_session, tmp_storage) == 1
    db_session.expire_all()
    assert db_session.get(Document, doc.id) is None
    assert not tmp_storage.exists(blob_key)

    actions = set(db_session.exec(select(AuditLog.action)).all())
    assert AuditAction.compliance_document_purged in actions


def test_retention_blocks_purge(db_session: Session, tmp_storage) -> None:  # noqa: ANN001
    owner = make_user(db_session, "p2@ex.com")
    project = make_project(db_session, owner)
    doc = make_document(
        db_session,
        project_id=project.id,
        created_by=owner.id,
        status=DocumentStatus.deleted,
        deleted_at=PAST,
        purge_after=PAST,
        retention_until=FUTURE_DATE,
    )
    make_version(db_session, tmp_storage, document_id=doc.id, created_by=owner.id)

    assert maintenance.purge_deleted_documents(db_session, tmp_storage) == 0
    assert db_session.get(Document, doc.id) is not None

    doc.retention_until = date(2020, 1, 1)
    db_session.add(doc)
    db_session.flush()
    assert maintenance.purge_deleted_documents(db_session, tmp_storage) == 1


def test_grace_period_blocks_purge(db_session: Session, tmp_storage) -> None:  # noqa: ANN001
    owner = make_user(db_session, "p3@ex.com")
    project = make_project(db_session, owner)
    future = datetime.now(UTC) + timedelta(days=10)
    doc = make_document(
        db_session,
        project_id=project.id,
        created_by=owner.id,
        status=DocumentStatus.deleted,
        deleted_at=datetime.now(UTC),
        purge_after=future,
    )
    make_version(db_session, tmp_storage, document_id=doc.id, created_by=owner.id)
    assert maintenance.purge_deleted_documents(db_session, tmp_storage) == 0
    assert db_session.get(Document, doc.id) is not None


# ---------- Export (Art. 15/20) ----------


def test_user_export_contains_pii(db_session: Session, tmp_storage, tmp_export_storage) -> None:  # noqa: ANN001
    user = make_user(db_session, "subject@ex.com", full_name="Erika Muster")
    project = make_project(db_session, user)
    doc = make_document(db_session, project_id=project.id, created_by=user.id, title="Mietvertrag")
    make_version(db_session, tmp_storage, document_id=doc.id, created_by=user.id)

    export = UserExport(
        subject_user_id=user.id,
        requested_by=user.id,
        status=ExportStatus.pending,
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    db_session.add(export)
    db_session.flush()

    assert maintenance.produce_export(db_session, export.id, tmp_export_storage) == "ready"
    db_session.expire_all()
    stored = db_session.get(UserExport, export.id)
    assert stored.status == ExportStatus.ready and stored.storage_key

    raw = b"".join(tmp_export_storage.open_stream(stored.storage_key))
    payload = json.loads(raw)
    assert payload["user"]["email"] == "subject@ex.com"
    assert payload["user"]["full_name"] == "Erika Muster"
    assert any(d["title"] == "Mietvertrag" for d in payload["documents_created"])
    assert len(payload["versions_created"]) == 1


def test_create_export_endpoint(client: TestClient, db_session: Session) -> None:
    admin = make_user(db_session, "admin2@ex.com", superadmin=True)
    subject = make_user(db_session, "sub2@ex.com")

    res = client.post(f"/api/admin/users/{subject.id}/export", headers=bearer(admin))
    assert res.status_code == 201
    assert res.json()["status"] == ExportStatus.pending

    actions = set(db_session.exec(select(AuditLog.action)).all())
    assert AuditAction.compliance_user_export_created in actions


def test_cleanup_expired_exports(db_session: Session, tmp_export_storage) -> None:  # noqa: ANN001
    user = make_user(db_session, "exp@ex.com")
    import io

    tmp_export_storage.save("old.json", io.BytesIO(b"{}"))
    export = UserExport(
        subject_user_id=user.id,
        requested_by=user.id,
        status=ExportStatus.ready,
        storage_key="old.json",
        expires_at=PAST,
    )
    db_session.add(export)
    db_session.flush()

    assert maintenance.cleanup_expired_exports(db_session, tmp_export_storage) == 1
    db_session.expire_all()
    stored = db_session.get(UserExport, export.id)
    assert stored.status == ExportStatus.expired
    assert stored.storage_key is None
    assert not tmp_export_storage.exists("old.json")


# ---------- User-Anonymisierung (Art. 17) ----------


def test_anonymize_user(client: TestClient, db_session: Session) -> None:
    admin = make_user(db_session, "super2@ex.com", superadmin=True)
    target = make_user(db_session, "victim@ex.com", full_name="Max Ziel")
    project = make_project(db_session, admin)
    db_session.add(ProjectMember(project_id=project.id, user_id=target.id, role="viewer"))
    db_session.add(
        RefreshToken(
            user_id=target.id,
            token_hash="dummyhash",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    db_session.flush()

    res = client.delete(f"/api/admin/users/{target.id}", headers=bearer(admin))
    assert res.status_code == 200

    db_session.expire_all()
    stored = db_session.get(type(target), target.id)
    assert stored.is_anonymized is True
    assert stored.is_active is False
    assert stored.full_name == ""
    assert stored.email.startswith("anonymized-")

    # Mitgliedschaften entfernt, Tokens widerrufen.
    assert (
        db_session.exec(select(ProjectMember).where(ProjectMember.user_id == target.id)).first()
        is None
    )
    token = db_session.exec(select(RefreshToken).where(RefreshToken.user_id == target.id)).first()
    assert token.revoked_at is not None

    actions = set(db_session.exec(select(AuditLog.action)).all())
    assert AuditAction.user_anonymized in actions


def test_cannot_anonymize_self(client: TestClient, db_session: Session) -> None:
    admin = make_user(db_session, "super3@ex.com", superadmin=True)
    res = client.delete(f"/api/admin/users/{admin.id}", headers=bearer(admin))
    assert res.status_code == 400


# ---------- Benutzer anlegen (Admin) ----------


def test_admin_create_user(client: TestClient, db_session: Session) -> None:
    admin = make_user(db_session, "super5@ex.com", superadmin=True)
    body = {"email": "neu@ex.com", "password": "geheim12345", "full_name": "Neu Nutzer"}

    res = client.post("/api/admin/users", json=body, headers=bearer(admin))
    assert res.status_code == 201, res.text
    assert res.json()["email"] == "neu@ex.com"

    # Neuer User kann sich einloggen.
    login = client.post("/api/auth/login", json={"email": "neu@ex.com", "password": "geheim12345"})
    assert login.status_code == 200

    # Doppelte E-Mail -> 409.
    dup = client.post("/api/admin/users", json=body, headers=bearer(admin))
    assert dup.status_code == 409

    actions = set(db_session.exec(select(AuditLog.action)).all())
    assert AuditAction.user_created in actions


def test_admin_create_user_requires_superadmin(client: TestClient, db_session: Session) -> None:
    normal = make_user(db_session, "normal2@ex.com")
    res = client.post(
        "/api/admin/users",
        json={"email": "x@ex.com", "password": "geheim12345", "full_name": "X"},
        headers=bearer(normal),
    )
    assert res.status_code == 403


# ---------- Admin-Zugriffsschutz + Audit-IP-Cleanup ----------


def test_admin_endpoints_require_superadmin(client: TestClient, db_session: Session) -> None:
    normal = make_user(db_session, "normal@ex.com")
    admin = make_user(db_session, "super4@ex.com", superadmin=True)

    assert client.get("/api/admin/users", headers=bearer(normal)).status_code == 403
    ok = client.get("/api/admin/users", headers=bearer(admin))
    assert ok.status_code == 200
    assert ok.json()["total"] >= 2


def test_rewrap_requires_superadmin(client: TestClient, db_session: Session) -> None:
    normal = make_user(db_session, "rewrap-normal@ex.com")
    res = client.post("/api/admin/storage/rewrap", headers=bearer(normal))
    assert res.status_code == 403


def test_cleanup_audit_ip_redacts_old_ip(db_session: Session) -> None:
    row = AuditLog(
        action=AuditAction.user_login,
        entity_type="user",
        ip_address="203.0.113.7",
        created_at=PAST,
    )
    db_session.add(row)
    db_session.flush()

    assert maintenance.cleanup_audit_ip(db_session, retention_days=30) == 1
    db_session.expire_all()
    stored = db_session.get(AuditLog, row.id)
    assert stored.ip_address is None
