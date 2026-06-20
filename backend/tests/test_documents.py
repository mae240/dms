"""Tests fuer Dokument-Upload, Versionierung und sichere Downloads."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from dms_core.config import settings
from dms_core.enums import AuditAction
from dms_core.models.audit import AuditLog
from tests.factories import bearer, make_document, make_user, make_version

TXT = b"Vertraulicher Vertragstext - Version 1"
TXT2 = b"Vertraulicher Vertragstext - Version 2 (geaendert)"


def _project_with_roles(client: TestClient, db_session: Session):
    owner = make_user(db_session, "o@example.com")
    editor = make_user(db_session, "e@example.com")
    viewer = make_user(db_session, "v@example.com")
    outsider = make_user(db_session, "x@example.com")
    pid = client.post("/api/projects", json={"name": "Kunde"}, headers=bearer(owner)).json()["id"]
    for email, role in (("e@example.com", "editor"), ("v@example.com", "viewer")):
        client.post(
            f"/api/projects/{pid}/members",
            json={"email": email, "role": role},
            headers=bearer(owner),
        )
    return pid, owner, editor, viewer, outsider


def _upload(client: TestClient, pid: str, headers: dict, content: bytes, title="Vertrag"):
    return client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("vertrag.txt", content, "text/plain")},
        data={"title": title},
        headers=headers,
    )


def test_upload_creates_v1_and_second_upload_creates_v2(client: TestClient, db_session: Session):
    pid, _owner, editor, _viewer, _outsider = _project_with_roles(client, db_session)

    res = _upload(client, pid, bearer(editor), TXT)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["current_version"]["version_number"] == 1
    assert body["current_version"]["processing_status"] == "uploaded"
    assert len(body["current_version"]["file_hash"]) == 64  # sha256 hex
    # storage_key darf NICHT nach aussen gelangen:
    assert "storage_key" not in body["current_version"]
    doc_id = body["id"]

    v2 = client.post(
        f"/api/documents/{doc_id}/versions",
        files={"file": ("vertrag.txt", TXT2, "text/plain")},
        headers=bearer(editor),
    )
    assert v2.status_code == 201
    assert v2.json()["version_number"] == 2

    versions = client.get(f"/api/documents/{doc_id}/versions", headers=bearer(editor)).json()
    assert [v["version_number"] for v in versions] == [2, 1]  # alte Version bleibt erhalten


def test_viewer_can_download_but_not_upload(client: TestClient, db_session: Session):
    pid, _owner, editor, viewer, _outsider = _project_with_roles(client, db_session)
    doc_id = _upload(client, pid, bearer(editor), TXT).json()["id"]

    dl = client.get(f"/api/documents/{doc_id}/download", headers=bearer(viewer))
    assert dl.status_code == 200
    assert dl.content == TXT
    assert "attachment" in dl.headers["content-disposition"]

    # Viewer darf nicht hochladen (editor erforderlich).
    forbidden = _upload(client, pid, bearer(viewer), TXT)
    assert forbidden.status_code == 403


def test_outsider_cannot_access_or_download(client: TestClient, db_session: Session):
    pid, _owner, editor, _viewer, outsider = _project_with_roles(client, db_session)
    doc_id = _upload(client, pid, bearer(editor), TXT).json()["id"]

    assert client.get(f"/api/documents/{doc_id}", headers=bearer(outsider)).status_code == 404
    assert (
        client.get(f"/api/documents/{doc_id}/download", headers=bearer(outsider)).status_code == 404
    )


def test_disallowed_mime_is_rejected_415(client: TestClient, db_session: Session):
    pid, _owner, editor, *_ = _project_with_roles(client, db_session)
    binary = bytes(range(256)) * 4  # magic erkennt application/octet-stream
    res = client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("payload.bin", binary, "application/octet-stream")},
        data={"title": "Boese Datei"},
        headers=bearer(editor),
    )
    assert res.status_code == 415


def test_oversize_upload_is_rejected_413(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
):
    pid, _owner, editor, *_ = _project_with_roles(client, db_session)
    monkeypatch.setattr(settings, "max_upload_bytes", 10)
    res = _upload(client, pid, bearer(editor), b"viel mehr als zehn bytes")
    assert res.status_code == 413


def test_reprocess_version(client: TestClient, db_session: Session, tmp_storage):  # noqa: ANN001
    pid, _owner, editor, viewer, _outsider = _project_with_roles(client, db_session)
    doc = make_document(db_session, project_id=uuid.UUID(pid), created_by=editor.id)
    version = make_version(db_session, tmp_storage, document_id=doc.id, created_by=editor.id)
    assert version.processing_status == "ready"

    # Editor darf neu verarbeiten -> Status zurueck auf 'uploaded'.
    res = client.post(f"/api/versions/{version.id}/reprocess", headers=bearer(editor))
    assert res.status_code == 200
    assert res.json()["processing_status"] == "uploaded"

    # Viewer darf nicht.
    assert (
        client.post(f"/api/versions/{version.id}/reprocess", headers=bearer(viewer)).status_code
        == 403
    )

    assert AuditAction.document_version_reprocessed in set(
        db_session.exec(select(AuditLog.action)).all()
    )


def test_audit_records_document_actions(client: TestClient, db_session: Session):
    pid, _owner, editor, viewer, _outsider = _project_with_roles(client, db_session)
    doc_id = _upload(client, pid, bearer(editor), TXT).json()["id"]
    client.get(f"/api/documents/{doc_id}/download", headers=bearer(viewer))

    actions = set(db_session.exec(select(AuditLog.action)).all())
    assert {
        AuditAction.document_uploaded,
        AuditAction.document_version_created,
        AuditAction.document_downloaded,
    } <= actions


def test_patch_status_lifecycle_active_archived(client: TestClient, db_session: Session):
    pid, _owner, editor, *_ = _project_with_roles(client, db_session)
    doc_id = _upload(client, pid, bearer(editor), TXT).json()["id"]

    # Aktiv -> archiviert.
    res = client.patch(
        f"/api/documents/{doc_id}",
        json={"status": "archived"},
        headers=bearer(editor),
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "archived"

    # Archiviert -> wieder aktiv.
    res = client.patch(
        f"/api/documents/{doc_id}",
        json={"status": "active"},
        headers=bearer(editor),
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "active"


def test_patch_status_deleted_rejected_422(client: TestClient, db_session: Session):
    pid, _owner, editor, *_ = _project_with_roles(client, db_session)
    doc_id = _upload(client, pid, bearer(editor), TXT).json()["id"]

    # 'deleted' laeuft nicht ueber metadata-patch, sondern ueber soft_delete/DELETE.
    res = client.patch(
        f"/api/documents/{doc_id}",
        json={"status": "deleted"},
        headers=bearer(editor),
    )
    assert res.status_code == 422, res.text


def test_patch_status_invalid_value_rejected_422(client: TestClient, db_session: Session):
    pid, _owner, editor, *_ = _project_with_roles(client, db_session)
    doc_id = _upload(client, pid, bearer(editor), TXT).json()["id"]

    res = client.patch(
        f"/api/documents/{doc_id}",
        json={"status": "bogus"},
        headers=bearer(editor),
    )
    assert res.status_code == 422, res.text


def test_upload_sets_default_retention(client: TestClient, db_session: Session):
    from datetime import date, timedelta

    pid, _owner, editor, *_ = _project_with_roles(client, db_session)
    res = client.post(
        f"/api/projects/{pid}/documents",
        data={"title": "Vertrag"},
        files={"file": ("v.txt", b"inhalt", "text/plain")},
        headers=bearer(editor),
    )
    assert res.status_code == 201, res.text
    expected = (date.today() + timedelta(days=settings.default_retention_days)).isoformat()
    assert res.json()["retention_until"] == expected
