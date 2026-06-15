"""Idempotentes Seed-Script fuer lokale Entwicklung.

Aufruf:  docker compose run --rm backend python -m app.seed

Legt an (nur falls noch nicht vorhanden):
- Superadmin + je einen Editor/Viewer
- Demo-Projekt mit allen Rollen + ein zweites, privates Projekt (nur Owner)
- ein Beispiel-Dokument mit fertig verarbeiteter Version
- Verzeichnis von Verarbeitungstaetigkeiten (Art. 30 VVT)
"""

from __future__ import annotations

import io
import os
import uuid

from sqlmodel import Session, select

from dms_core.audit import write_audit_log
from dms_core.config import settings
from dms_core.db import engine
from dms_core.enums import AuditAction, ProcessingStatus, ProjectRole
from dms_core.files import sha256_of_chunks
from dms_core.models.compliance import ProcessingActivity
from dms_core.models.document import Document, DocumentVersion
from dms_core.models.project import Project, ProjectMember
from dms_core.models.user import User
from dms_core.security import hash_password
from dms_core.storage import get_storage

ADMIN_EMAIL = "admin@dms.local"


def _seed_password(env_var: str, dev_default: str) -> str:
    """Seed-Passwort aus der Umgebung lesen.

    In production MUSS die Env-Variable gesetzt sein (sonst RuntimeError) — der
    Dev-Default verhindert versehentlich schwache Passwoerter in Prod.
    """
    value = os.environ.get(env_var)
    if value:
        return value
    if settings.environment == "production":
        raise RuntimeError(f"{env_var} muss in production gesetzt sein")
    return dev_default


ADMIN_PASSWORD = _seed_password("SEED_ADMIN_PASSWORD", "adminpass123")
DEMO_PASSWORD = _seed_password("SEED_DEMO_PASSWORD", "demopass123")


def _get_or_create_user(
    session: Session, email: str, *, full_name: str, password: str, superadmin: bool = False
) -> User:
    user = session.exec(select(User).where(User.email == email)).first()
    if user:
        return user
    user = User(
        email=email,
        full_name=full_name,
        hashed_password=hash_password(password),
        is_superadmin=superadmin,
    )
    session.add(user)
    session.flush()
    print(f"  + User {email}")
    return user


def _get_or_create_project(session: Session, name: str, owner: User) -> tuple[Project, bool]:
    project = session.exec(
        select(Project).where(Project.name == name, Project.owner_id == owner.id)
    ).first()
    if project:
        return project, False
    project = Project(name=name, owner_id=owner.id, description=f"Seed-Projekt: {name}")
    session.add(project)
    session.flush()
    session.add(ProjectMember(project_id=project.id, user_id=owner.id, role=ProjectRole.owner))
    write_audit_log(
        session,
        action=AuditAction.project_created,
        entity_type="project",
        actor_user_id=owner.id,
        entity_id=project.id,
        project_id=project.id,
        metadata={"name": name, "seed": True},
    )
    print(f"  + Projekt {name}")
    return project, True


def _ensure_member(session: Session, project: Project, user: User, role: ProjectRole) -> None:
    existing = session.exec(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id, ProjectMember.user_id == user.id
        )
    ).first()
    if existing:
        return
    session.add(ProjectMember(project_id=project.id, user_id=user.id, role=role))
    write_audit_log(
        session,
        action=AuditAction.project_member_added,
        entity_type="project_member",
        actor_user_id=project.owner_id,
        entity_id=user.id,
        project_id=project.id,
        metadata={"role": role.value, "seed": True},
    )
    print(f"    + Mitglied {user.email} ({role})")


def _ensure_demo_document(session: Session, project: Project, author: User) -> None:
    existing = session.exec(
        select(Document).where(Document.project_id == project.id, Document.title == "Rahmenvertrag")
    ).first()
    if existing:
        return

    content = (
        b"RAHMENVERTRAG\n\n"
        b"Zwischen der Beispiel GmbH und dem Kunden.\n"
        b"Paragraph 1: Leistungsumfang.\n"
        b"Paragraph 2: Laufzeit 12 Monate.\n"
    )

    document = Document(
        id=uuid.uuid4(),
        project_id=project.id,
        title="Rahmenvertrag",
        description="Beispiel-Dokument aus dem Seed",
        category="Vertrag",
        created_by=author.id,
    )
    version_id = uuid.uuid4()
    storage_key = f"{document.id}/{version_id}"
    get_storage().save(storage_key, io.BytesIO(content))

    version = DocumentVersion(
        id=version_id,
        document_id=document.id,
        version_number=1,
        file_name="rahmenvertrag.txt",
        file_hash=sha256_of_chunks([content]),
        storage_key=storage_key,
        mime_type="text/plain",
        size_bytes=len(content),
        processing_status=ProcessingStatus.ready,
        created_by=author.id,
    )
    session.add(document)
    session.add(version)
    write_audit_log(
        session,
        action=AuditAction.document_uploaded,
        entity_type="document",
        actor_user_id=author.id,
        entity_id=document.id,
        project_id=project.id,
        metadata={"title": "Rahmenvertrag", "seed": True},
    )
    print("    + Dokument 'Rahmenvertrag' (Version 1, ready)")


def _ensure_processing_activities(session: Session) -> None:
    activities = [
        {
            "name": "Dokumentenverwaltung",
            "purpose": "Verwaltung und Versionierung von Vertrags- und Projektdokumenten",
            "legal_basis": "Art. 6 Abs. 1 lit. b DSGVO (Vertrag)",
            "data_categories": ["Dokumentinhalte", "Metadaten", "Ersteller"],
            "retention_policy": "Bis Widerruf / Ablauf der Aufbewahrungsfrist, dann Purge",
        },
        {
            "name": "Benutzerkonten & Authentifizierung",
            "purpose": "Anmeldung, Zugriffskontrolle, Audit",
            "legal_basis": "Art. 6 Abs. 1 lit. b/f DSGVO",
            "data_categories": ["E-Mail", "Name", "Login-Zeitpunkte", "IP-Adresse"],
            "retention_policy": "Konto bis Loeschung; Audit-IP 90 Tage",
        },
    ]
    for a in activities:
        exists = session.exec(
            select(ProcessingActivity).where(ProcessingActivity.name == a["name"])
        ).first()
        if exists:
            continue
        session.add(ProcessingActivity(**a))
        print(f"  + Verarbeitungstaetigkeit '{a['name']}'")


def main() -> None:
    print("Seeding …")
    with Session(engine) as session:
        admin = _get_or_create_user(
            session, ADMIN_EMAIL, full_name="Admin", password=ADMIN_PASSWORD, superadmin=True
        )
        editor = _get_or_create_user(
            session, "editor@demo.local", full_name="Erika Editor", password=DEMO_PASSWORD
        )
        viewer = _get_or_create_user(
            session, "viewer@demo.local", full_name="Viktor Viewer", password=DEMO_PASSWORD
        )

        demo, _ = _get_or_create_project(session, "Kunde Demo GmbH", admin)
        _ensure_member(session, demo, editor, ProjectRole.editor)
        _ensure_member(session, demo, viewer, ProjectRole.viewer)
        _ensure_demo_document(session, demo, admin)

        # Zweites, privates Projekt — beweist Projekt-Isolation (Art. 25):
        _get_or_create_project(session, "Intern (Privat)", admin)

        _ensure_processing_activities(session)
        session.commit()

    print("\nFertig. Login:")
    print(f"  Admin  : {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print(f"  Editor : editor@demo.local / {DEMO_PASSWORD}")
    print(f"  Viewer : viewer@demo.local / {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
