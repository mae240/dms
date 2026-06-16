"""Tests fuer /me/recent-documents (projektuebergreifend, mitgliedsgebunden)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session

from dms_core.enums import DocumentStatus
from tests.factories import bearer, make_document, make_project, make_user


def test_recent_documents_scoped_to_membership(client: TestClient, db_session: Session) -> None:
    owner = make_user(db_session, "rec-owner@example.com")
    outsider = make_user(db_session, "rec-outsider@example.com")

    project = make_project(db_session, owner)
    make_document(db_session, project_id=project.id, created_by=owner.id, title="Sichtbar")
    make_document(
        db_session,
        project_id=project.id,
        created_by=owner.id,
        title="Geloescht",
        status=DocumentStatus.deleted,
    )

    # Fremdes Projekt mit Dokument -> darf NICHT erscheinen.
    foreign = make_project(db_session, outsider, name="Fremd")
    make_document(db_session, project_id=foreign.id, created_by=outsider.id, title="Fremd-Doc")

    res = client.get("/api/me/recent-documents", headers=bearer(owner))
    assert res.status_code == 200
    titles = [d["title"] for d in res.json()]
    assert "Sichtbar" in titles
    assert "Geloescht" not in titles
    assert "Fremd-Doc" not in titles
    assert all(d["project_name"] == project.name for d in res.json())
