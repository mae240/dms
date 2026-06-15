"""add project status

Revision ID: a08116197a07
Revises: a3f1c0de0003
Create Date: 2026-06-14 23:59:43.243636+00:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401  (von autogenerierten SQLModel-Typen benoetigt)
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a08116197a07'
down_revision: str | None = 'a3f1c0de0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('status', sa.String(length=20), server_default='active', nullable=False))
    op.create_index(op.f('ix_projects_status'), 'projects', ['status'], unique=False)
    op.create_check_constraint(
        op.f('ck_projects_status_valid'),
        'projects',
        "status IN ('active', 'archived', 'deleted')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_projects_status_valid'), 'projects', type_='check')
    op.drop_index(op.f('ix_projects_status'), table_name='projects')
    op.drop_column('projects', 'status')
