"""Providerneutrale Storage-Abstraktion.

Bewusst SCHMAL und S3-frei gehalten, damit lokal, Hetzner Storage Box (SFTP/
WebDAV/Mount) und optional S3/MinIO ohne API-/DB-Aenderung austauschbar sind:
- nur OPAKE, relative storage_keys (nie absolute Pfade/URLs)
- KEINE presigned-URL-/bucket-/region-/multipart-Methoden
- Downloads laufen IMMER serverseitig durch die App (StreamingResponse)

Backend-Kontrakt:
- save() muss "atomar-oder-Fehlschlag" sein (kein halb geschriebener Blob).
- open() muss einen eigenstaendigen Stream-Kontext liefern; bei Remote-Backends
  (SFTP) eine eigene Connection pro Download, die im finally geschlossen wird.
- delete() muss idempotent sein (Loeschen eines fehlenden Keys = no-op).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import BinaryIO, Protocol, runtime_checkable


class StorageError(Exception):
    """Allgemeiner Storage-Fehler."""


class StorageKeyError(StorageError):
    """Ungueltiger oder unsicherer storage_key (z.B. Path-Traversal)."""


@runtime_checkable
class StorageBackend(Protocol):
    def save(self, key: str, stream: BinaryIO) -> str:
        """Schreibt den Stream unter `key` (atomar). Gibt den Key zurueck."""
        ...

    def open_stream(self, key: str, *, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        """Liefert die Bytes des Objekts als Iterator (fuer StreamingResponse)."""
        ...

    def delete(self, key: str) -> None:
        """Loescht das Objekt (idempotent)."""
        ...

    def exists(self, key: str) -> bool: ...

    def size(self, key: str) -> int: ...
