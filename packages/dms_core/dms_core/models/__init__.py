"""Alle SQLModel-Tabellen — eine einzige Schema-Quelle.

WICHTIG: `dms_core.db` wird zuerst importiert, damit die Naming-Convention
auf SQLModel.metadata gesetzt ist, BEVOR die ersten Tabellen-/Constraint-
Objekte erzeugt werden. Alembic-env.py importiert dieses Paket, damit
autogenerate alle Tabellen sieht.
"""

from __future__ import annotations

import dms_core.db  # noqa: F401  (setzt naming_convention auf der MetaData)
from dms_core.models.audit import AuditLog
from dms_core.models.compliance import ProcessingActivity
from dms_core.models.document import Document, DocumentVersion
from dms_core.models.export import UserExport
from dms_core.models.project import Project, ProjectMember
from dms_core.models.user import RefreshToken, User

__all__ = [
    "AuditLog",
    "Document",
    "DocumentVersion",
    "ProcessingActivity",
    "Project",
    "ProjectMember",
    "RefreshToken",
    "User",
    "UserExport",
]
