"""Datei-Hilfsfunktionen: Magic-Byte-MIME-Erkennung und SHA-256.

Genutzt vom Backend (Upload-Validierung) und vom Worker (Reverify).
python-magic benoetigt die System-Bibliothek libmagic (in den Images installiert).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import BinaryIO

import magic

_MAGIC = magic.Magic(mime=True)
HEAD_BYTES = 2048  # ausreichend fuer Magic-Byte-Erkennung


class UploadTooLarge(Exception):
    """Der hochgeladene Stream ueberschreitet das erlaubte Maximum."""


def guess_mime_from_bytes(data: bytes) -> str:
    """Erkennt den MIME-Typ anhand der Magic-Bytes (nicht der Dateiendung)."""
    return _MAGIC.from_buffer(data)


def sha256_of_chunks(chunks: Iterable[bytes]) -> str:
    """Berechnet den SHA-256-Hex-Digest ueber einen Byte-Iterator (chunked)."""
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return digest.hexdigest()


class HashingLimitedReader:
    """File-like Wrapper: zaehlt Bytes (mit Limit) und berechnet SHA-256 beim Lesen.

    Wird an StorageBackend.save() uebergeben — so wird der Upload nur EINMAL
    gelesen (streamend), waehrend Groesse, Limit und Hash gleichzeitig bestimmt
    werden. Bei Ueberschreitung wird UploadTooLarge geworfen (RAM/Disk-Schutz).
    """

    def __init__(self, src: BinaryIO, *, max_bytes: int) -> None:
        self._src = src
        self._max = max_bytes
        self._digest = hashlib.sha256()
        self.size = 0

    def read(self, n: int = -1) -> bytes:
        chunk = self._src.read(n)
        if chunk:
            self.size += len(chunk)
            if self.size > self._max:
                raise UploadTooLarge()
            self._digest.update(chunk)
        return chunk

    def hexdigest(self) -> str:
        return self._digest.hexdigest()
