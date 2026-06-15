"""Lokales Dateisystem-Backend (MVP).

Per gemountetem Pfad (CIFS/SFTP-Mount der Hetzner Storage Box) faktisch auch
produktiv tauglich. Atomares Schreiben via temp + os.replace, Path-Traversal-
Schutz, restriktive Dateirechte.
"""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

from dms_core.storage.base import StorageError, StorageKeyError


class LocalFilesystemBackend:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        if not key or key.startswith("/") or ".." in key.split("/"):
            raise StorageKeyError(f"Unsicherer storage_key: {key!r}")
        target = (self._root / key).resolve()
        # Sicherstellen, dass der Pfad innerhalb des Roots bleibt:
        if not str(target).startswith(str(self._root) + os.sep):
            raise StorageKeyError(f"Path-Traversal erkannt: {key!r}")
        return target

    def save(self, key: str, stream: BinaryIO) -> str:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.parent / f".{uuid.uuid4().hex}.tmp"
        try:
            with open(tmp, "wb") as fh:
                shutil.copyfileobj(stream, fh, length=1024 * 1024)
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, target)  # atomar auf demselben Dateisystem
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise StorageError(f"Schreiben fehlgeschlagen fuer {key!r}: {exc}") from exc
        except BaseException:
            # z.B. UploadTooLarge aus dem Reader — Original-Exception erhalten,
            # nur den unvollstaendigen Temp-Blob aufraeumen.
            tmp.unlink(missing_ok=True)
            raise
        return key

    def open_stream(self, key: str, *, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        target = self._resolve(key)
        if not target.is_file():
            raise StorageError(f"Objekt nicht gefunden: {key!r}")

        def _iter() -> Iterator[bytes]:
            with open(target, "rb") as fh:
                while chunk := fh.read(chunk_size):
                    yield chunk

        return _iter()

    def delete(self, key: str) -> None:
        try:
            self._resolve(key).unlink(missing_ok=True)  # idempotent
        except StorageKeyError:
            raise
        except OSError as exc:
            raise StorageError(f"Loeschen fehlgeschlagen fuer {key!r}: {exc}") from exc

    def exists(self, key: str) -> bool:
        try:
            return self._resolve(key).is_file()
        except StorageKeyError:
            return False

    def size(self, key: str) -> int:
        target = self._resolve(key)
        if not target.is_file():
            raise StorageError(f"Objekt nicht gefunden: {key!r}")
        return target.stat().st_size
