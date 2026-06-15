"""Enums und Rollen-Hierarchie.

Enums werden in der DB als VARCHAR + CHECK gespeichert (nicht als native
Postgres-ENUMs) — das vermeidet Alembic-Schmerz bei spaeteren Wertaenderungen.
"""

from __future__ import annotations

from enum import StrEnum


class ProjectRole(StrEnum):
    owner = "owner"
    admin = "admin"
    editor = "editor"
    viewer = "viewer"


# Hierarchie (hoeher = mehr Rechte). Genutzt von require_project_role(min_role).
ROLE_ORDER: dict[str, int] = {
    ProjectRole.viewer: 0,
    ProjectRole.editor: 1,
    ProjectRole.admin: 2,
    ProjectRole.owner: 3,
}


def role_satisfies(actual: str, minimum: str) -> bool:
    """True, wenn `actual` mindestens so viel Recht hat wie `minimum`."""
    return ROLE_ORDER.get(actual, -1) >= ROLE_ORDER.get(minimum, 99)


class ProjectStatus(StrEnum):
    active = "active"
    archived = "archived"
    deleted = "deleted"


class DocumentStatus(StrEnum):
    active = "active"
    archived = "archived"
    deleted = "deleted"


class ProcessingStatus(StrEnum):
    uploaded = "uploaded"
    processing = "processing"
    ready = "ready"
    failed = "failed"
    quarantined = "quarantined"


class ExportStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"
    expired = "expired"


class AuditAction(StrEnum):
    """Kanonische Audit-Aktionen (Art. 30 Nachvollziehbarkeit)."""

    user_login = "user.login"
    user_login_failed = "user.login_failed"
    user_logout = "user.logout"
    user_created = "user.created"
    user_anonymized = "user.anonymized"
    user_password_changed = "user.password_changed"
    document_uploaded = "document.uploaded"
    document_version_created = "document.version_created"
    document_version_reprocessed = "document.version_reprocessed"
    document_downloaded = "document.downloaded"
    document_deleted = "document.deleted"
    document_restored = "document.restored"
    document_metadata_updated = "document.metadata_updated"
    document_purged = "document.purged"
    document_auto_expired = "document.auto_expired"
    project_created = "project.created"
    project_updated = "project.updated"
    project_deleted = "project.deleted"
    project_restored = "project.restored"
    project_member_added = "project.member_added"
    project_member_removed = "project.member_removed"
    project_member_role_changed = "project.member_role_changed"
    compliance_user_export_created = "compliance.user_export_created"
    compliance_user_export_downloaded = "compliance.user_export_downloaded"
    compliance_retention_set = "compliance.retention_set"
    compliance_legal_hold_set = "compliance.legal_hold_set"
    compliance_document_purged = "compliance.document_purged"


def enum_check(values: type[StrEnum]) -> str:
    """Hilfsausdruck fuer CHECK-Constraints in Migrationen."""
    joined = ", ".join(f"'{v.value}'" for v in values)
    return f"IN ({joined})"
