"""Storage-Factory: liefert das konfigurierte Backend.

MVP: 'local'. 'sftp' (Hetzner Storage Box direkt) ist als naechstes Backend
vorgesehen und kann hier additiv ergaenzt werden, ohne API/DB zu aendern.
"""

from __future__ import annotations

from functools import lru_cache

from dms_core.config import settings
from dms_core.storage.base import StorageBackend, StorageError, StorageKeyError
from dms_core.storage.encrypted import EncryptedStorageBackend
from dms_core.storage.local import LocalFilesystemBackend


def _maybe_encrypt(backend: StorageBackend) -> StorageBackend:
    """Umhuellt das Backend transparent mit AES-256-GCM, sofern ein Keyring gesetzt ist."""
    ring = settings.storage_keyring
    if ring:
        return EncryptedStorageBackend(
            backend, keyring=ring, active_key_id=settings.storage_active_key_id
        )
    return backend


@lru_cache
def get_storage() -> StorageBackend:
    if settings.storage_backend == "local":
        return _maybe_encrypt(LocalFilesystemBackend(settings.storage_root))
    raise StorageError(f"Unbekanntes STORAGE_BACKEND: {settings.storage_backend!r}")


@lru_cache
def get_export_storage() -> StorageBackend:
    """Separater Bereich fuer Export-Dateien (PII, kurzlebig)."""
    return _maybe_encrypt(LocalFilesystemBackend(settings.export_root))


__all__ = [
    "StorageBackend",
    "StorageError",
    "StorageKeyError",
    "get_export_storage",
    "get_storage",
]
