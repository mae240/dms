"""add file_name to document_versions

Revision ID: 6f826ad78867
Revises: 2a4660993b0b
Create Date: 2026-06-14 22:11:13.290624+00:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401  (von autogenerierten SQLModel-Typen benoetigt)
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '6f826ad78867'
down_revision: str | None = '2a4660993b0b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drei-Schritt, damit die Migration auch auf DBs mit existierenden
    # document_versions-Zeilen laeuft:
    # 1) Spalte nullable anlegen
    op.add_column('document_versions', sa.Column('file_name', sa.String(length=400), nullable=True))
    # 2) Backfill: Dokumenttitel als bestmoeglicher Anzeigename (title ist
    #    String(300), passt in String(400)); Fallback fuer alle Restfaelle
    op.execute(
        """
        UPDATE document_versions dv
        SET file_name = d.title
        FROM documents d
        WHERE d.id = dv.document_id
          AND dv.file_name IS NULL
        """
    )
    op.execute("UPDATE document_versions SET file_name = 'unbenannt' WHERE file_name IS NULL")
    # 3) NOT NULL setzen -> Endschema identisch zur bisherigen Revision
    op.alter_column('document_versions', 'file_name', existing_type=sa.String(length=400), nullable=False)


def downgrade() -> None:
    op.drop_column('document_versions', 'file_name')
