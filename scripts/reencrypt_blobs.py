"""Einmal-Migration: bestehende Klartext-Blobs at-rest verschluesseln (aktive Version).

Idempotent (DMSENC1-Header wird uebersprungen). Lauf NACH dem Setzen des Keyrings:
    docker compose run --rm backend python /app/scripts/reencrypt_blobs.py
"""

from __future__ import annotations

import io
import sys

from sqlmodel import Session, select

from dms_core.config import settings
from dms_core.db import engine
from dms_core.models.document import DocumentVersion
from dms_core.storage.encrypted import _MAGIC, EncryptedStorageBackend  # noqa: PLC2701
from dms_core.storage.local import LocalFilesystemBackend


def main() -> int:
    if not settings.storage_keyring:
        print("Kein Keyring gesetzt — nichts zu tun.")
        return 1
    raw = LocalFilesystemBackend(settings.storage_root)
    enc = EncryptedStorageBackend(
        raw, keyring=settings.storage_keyring, active_key_id=settings.storage_active_key_id
    )
    with Session(engine) as session:
        keys = [v.storage_key for v in session.exec(select(DocumentVersion)).all()]

    migrated = skipped = 0
    for key in keys:
        if not raw.exists(key):
            continue
        head = b"".join(raw.open_stream(key, chunk_size=len(_MAGIC)))[: len(_MAGIC)]
        if head == _MAGIC:
            skipped += 1
            continue
        plaintext = b"".join(raw.open_stream(key))
        enc.save(key, io.BytesIO(plaintext))
        migrated += 1
    print(f"Fertig: {migrated} verschluesselt, {skipped} bereits verschluesselt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
