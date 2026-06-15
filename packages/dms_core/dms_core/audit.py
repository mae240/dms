"""Audit-Logging-Helper (Art. 30 Nachvollziehbarkeit).

write_audit_log() fuegt einen Eintrag in derselben Transaktion wie die
ausloesende Aktion hinzu (nicht committen — das uebernimmt der Aufrufer/Scope).
Metadata wird auf unkritische Felder beschraenkt: NIE Passwoerter, Tokens oder
Dokumentinhalte loggen.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlmodel import Session

from dms_core.models.audit import AuditLog

# Schluessel, die niemals ins Audit-Log gelangen duerfen:
_FORBIDDEN_META_KEYS = {"password", "token", "refresh_token", "hashed_password", "extracted_text"}


def _sanitize(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return None
    return {k: v for k, v in metadata.items() if k.lower() not in _FORBIDDEN_META_KEYS}


def write_audit_log(
    session: Session,
    *,
    action: str,
    entity_type: str,
    actor_user_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    ip_address: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        ip_address=ip_address,
        metadata_=_sanitize(metadata),
    )
    session.add(entry)
    session.flush()  # ID verfuegbar, aber Commit bleibt beim Aufrufer
    return entry
