"""add search and audit perf indexes

Revision ID: 2419198ea4ed
Revises: a08116197a07
Create Date: 2026-06-15 02:30:00.000000+00:00

Performance-Indizes aus Review-Findings:
- H6: pg_trgm-GIN-Index auf documents.title fuer ILIKE '%term%' (leading wildcard).
- M8: B-Tree-Index auf audit_logs.actor_user_id (FK ohne Index -> Full-Scan
  beim Art-15-Export, WHERE actor_user_id = ?).
- Audit-Hot-Path: Composite-Index (project_id, created_at DESC) fuer
  Filter-nach-Projekt + Sortierung neueste-zuerst.

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401  (von autogenerierten SQLModel-Typen benoetigt)


# revision identifiers, used by Alembic.
revision: str = '2419198ea4ed'
down_revision: str | None = 'a08116197a07'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # H6: Trigram-Suche auf Dokumenttitel (Extension vor dem Index erzeugen).
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index(
        "ix_documents_title_trgm",
        "documents",
        ["title"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )

    # M8: FK actor_user_id indizieren (Art-15-Export).
    op.create_index(
        "ix_audit_logs_actor_user_id",
        "audit_logs",
        ["actor_user_id"],
        unique=False,
    )

    # Audit-Hot-Path: Filter nach Projekt + Sortierung neueste-zuerst.
    op.create_index(
        "ix_audit_logs_project_created",
        "audit_logs",
        ["project_id", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_project_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_user_id", table_name="audit_logs")
    op.drop_index(
        "ix_documents_title_trgm",
        table_name="documents",
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    # Extension NICHT droppen (kann von anderen Objekten genutzt werden).
