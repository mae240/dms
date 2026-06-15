"""audit_logs: erlaube IP-Schwaerzung (Retention), sonst weiter append-only

Revision ID: a3f1c0de0003
Revises: 6f826ad78867
Create Date: 2026-06-15 00:00:00.000000+00:00

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a3f1c0de0003"
down_revision: str | None = "6f826ad78867"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REDACTION_FN = """
CREATE OR REPLACE FUNCTION dms_block_audit_mutation() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' OR TG_OP = 'TRUNCATE' THEN
        RAISE EXCEPTION 'audit_logs ist append-only: % ist nicht erlaubt', TG_OP;
    END IF;
    -- UPDATE: ausschliesslich das Schwaerzen der IP-Adresse (Speicherbegrenzung,
    -- Art. 5) ist erlaubt; alle inhaltlichen Felder bleiben unveraenderlich.
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.actor_user_id IS DISTINCT FROM OLD.actor_user_id
       OR NEW.action IS DISTINCT FROM OLD.action
       OR NEW.entity_type IS DISTINCT FROM OLD.entity_type
       OR NEW.entity_id IS DISTINCT FROM OLD.entity_id
       OR NEW.project_id IS DISTINCT FROM OLD.project_id
       OR NEW.metadata IS DISTINCT FROM OLD.metadata
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'audit_logs ist append-only: nur IP-Schwaerzung erlaubt';
    END IF;
    IF NEW.ip_address IS NOT NULL THEN
        RAISE EXCEPTION 'audit_logs: ip_address darf nur auf NULL gesetzt werden';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_BLOCK_ALL_FN = """
CREATE OR REPLACE FUNCTION dms_block_audit_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs ist append-only: % ist nicht erlaubt', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(_REDACTION_FN)


def downgrade() -> None:
    op.execute(_BLOCK_ALL_FN)
