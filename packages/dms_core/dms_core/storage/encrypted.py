"""Transparente At-rest-Verschluesselung als StorageBackend-Decorator.

Gerahmtes AES-256-GCM (64-KB-Frames) mit Envelope-Verschluesselung: pro Blob ein
zufaelliger Data-Key (DEK), umschlossen mit einem Master-Key aus dem Keyring.
Der Header traegt die Key-Versions-ID -> Rotation ohne Datei-Neuverschluesselung
(rewrap() schluesselt nur den DEK um). Streamend; AAD bindet Frame-Index + Ende.
"""

from __future__ import annotations

import os
import struct
import tempfile
from collections.abc import Iterator
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from dms_core.storage.base import StorageBackend, StorageError

_MAGIC = b"DMSENC1\x00"
_FRAME = 64 * 1024
_NONCE = 12
_WRAPPED_DEK = 48  # 32-Byte-DEK + 16-Byte-Tag
_KEYID = struct.Struct(">I")
_AAD = struct.Struct(">QB")
_HDR = struct.Struct(">B")
_LEN = struct.Struct(">I")


class _IterReader:
    """Byte-Iterator -> .read(n)-faehiges Objekt (fuer inner.save())."""

    def __init__(self, it: Iterator[bytes]) -> None:
        self._it = it
        self._buf = bytearray()
        self._eof = False

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            out = bytes(self._buf) + b"".join(self._it)
            self._buf = bytearray()
            self._eof = True
            return out
        while len(self._buf) < n and not self._eof:
            try:
                self._buf.extend(next(self._it))
            except StopIteration:
                self._eof = True
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out


class _FrameReader:
    """Liest exakte Byte-Mengen aus einem Iterator; erkennt vorzeitiges Ende."""

    def __init__(self, it: Iterator[bytes]) -> None:
        self._it = it
        self._buf = bytearray()
        self._eof = False

    def _fill(self, n: int) -> None:
        while len(self._buf) < n and not self._eof:
            try:
                self._buf.extend(next(self._it))
            except StopIteration:
                self._eof = True

    def read_exact(self, n: int) -> bytes:
        self._fill(n)
        if len(self._buf) < n:
            raise StorageError("Verschluesselter Blob unvollstaendig/abgeschnitten")
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out

    def at_eof(self) -> bool:
        self._fill(1)
        return len(self._buf) == 0

    def drain(self) -> Iterator[bytes]:
        if self._buf:
            yield bytes(self._buf)
            self._buf = bytearray()
        yield from self._it


class EncryptedStorageBackend:
    def __init__(
        self, inner: StorageBackend, *, keyring: dict[int, bytes], active_key_id: int
    ) -> None:
        for kid, key in keyring.items():
            if len(key) != 32:
                raise ValueError(f"Master-Key {kid} muss genau 32 Bytes sein")
        if active_key_id not in keyring:
            raise ValueError("aktive Key-Version ist nicht im Keyring")
        self._inner = inner
        self._keyring = dict(keyring)
        self._active = active_key_id
        self._active_aes = AESGCM(keyring[active_key_id])

    # ---- Schreiben ----

    def _encrypt(self, plaintext: BinaryIO) -> Iterator[bytes]:
        dek = AESGCM.generate_key(bit_length=256)
        aes = AESGCM(dek)
        wrap_nonce = os.urandom(_NONCE)
        yield (
            _MAGIC
            + _KEYID.pack(self._active)
            + wrap_nonce
            + self._active_aes.encrypt(wrap_nonce, dek, None)
        )
        index = 0
        prev = plaintext.read(_FRAME)
        while True:
            nxt = plaintext.read(_FRAME)
            final = 1 if not nxt else 0
            nonce = os.urandom(_NONCE)
            ct = aes.encrypt(nonce, prev, _AAD.pack(index, final))
            yield _HDR.pack(final) + nonce + _LEN.pack(len(ct)) + ct
            if final:
                break
            prev = nxt
            index += 1

    def save(self, key: str, stream: BinaryIO) -> str:
        return self._inner.save(key, _IterReader(self._encrypt(stream)))

    # ---- Lesen ----

    def _read_header(self, r: _FrameReader) -> bytes:
        """Liest Header, gibt den DEK zurueck."""
        if r.read_exact(len(_MAGIC)) != _MAGIC:
            raise StorageError("Kein gueltiger DMS-Verschluesselungs-Header")
        (key_id,) = _KEYID.unpack(r.read_exact(_KEYID.size))
        wrap_nonce = r.read_exact(_NONCE)
        wrapped = r.read_exact(_WRAPPED_DEK)
        master = self._keyring.get(key_id)
        if master is None:
            raise StorageError(f"Unbekannte Key-Version {key_id} (Keyring unvollstaendig?)")
        try:
            return AESGCM(master).decrypt(wrap_nonce, wrapped, None)
        except InvalidTag as exc:
            raise StorageError(
                "DEK-Entschluesselung fehlgeschlagen (falscher Master-Key?)"
            ) from exc

    def _decrypt(self, it: Iterator[bytes]) -> Iterator[bytes]:
        r = _FrameReader(it)
        dek = self._read_header(r)
        aes = AESGCM(dek)
        index = 0
        while True:
            (final,) = _HDR.unpack(r.read_exact(1))
            nonce = r.read_exact(_NONCE)
            (clen,) = _LEN.unpack(r.read_exact(_LEN.size))
            if clen > _FRAME + 16:  # max. ein Plaintext-Frame + GCM-Tag
                raise StorageError("Blob-Rahmenlaenge ungueltig (Manipulation?)")
            ct = r.read_exact(clen)
            try:
                yield aes.decrypt(nonce, ct, _AAD.pack(index, final))
            except InvalidTag as exc:
                raise StorageError("Blob-Integritaet verletzt (Manipulation?)") from exc
            if final:
                break
            index += 1
        if not r.at_eof():
            raise StorageError("Ueberzaehlige Daten nach finalem Frame (Manipulation?)")

    def open_stream(self, key: str, *, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        return self._decrypt(self._inner.open_stream(key, chunk_size=chunk_size))

    # ---- Rotation ----

    def rewrap(self, key: str) -> bool:
        """Schluesselt den DEK auf die aktive Key-Version um, OHNE die Frames neu
        zu verschluesseln (Body wird unveraendert kopiert). False, wenn schon aktiv."""
        r = _FrameReader(self._inner.open_stream(key))
        if r.read_exact(len(_MAGIC)) != _MAGIC:
            raise StorageError("Kein gueltiger Header")
        (key_id,) = _KEYID.unpack(r.read_exact(_KEYID.size))
        wrap_nonce = r.read_exact(_NONCE)
        wrapped = r.read_exact(_WRAPPED_DEK)
        if key_id == self._active:
            return False
        master = self._keyring.get(key_id)
        if master is None:
            raise StorageError(f"Unbekannte Key-Version {key_id}")
        try:
            dek = AESGCM(master).decrypt(wrap_nonce, wrapped, None)
        except InvalidTag as exc:
            raise StorageError("DEK-Entschluesselung fehlgeschlagen") from exc
        new_nonce = os.urandom(_NONCE)
        new_header = (
            _MAGIC
            + _KEYID.pack(self._active)
            + new_nonce
            + self._active_aes.encrypt(new_nonce, dek, None)
        )

        # Re-wrappten Inhalt vollstaendig in eine Disk-Temp-Datei draining, BEVOR
        # inner.save() denselben Key oeffnet: entkoppelt Lesen/Schreiben desselben
        # Keys -> backend-unabhaengig sicher (kein Source-Verlust bei Backends, die
        # das Ziel vor dem Leeren der Quelle zum Schreiben oeffnen). TemporaryFile
        # liegt immer auf Disk (kein RAM-Puffer bis 50 MB).
        with tempfile.TemporaryFile() as tmp:
            tmp.write(new_header)
            for chunk in r.drain():  # restliche Frames unveraendert
                tmp.write(chunk)
            tmp.seek(0)
            self._inner.save(key, tmp)
        return True

    # ---- Pass-through ----

    def delete(self, key: str) -> None:
        self._inner.delete(key)

    def exists(self, key: str) -> bool:
        return self._inner.exists(key)

    def size(self, key: str) -> int:
        return self._inner.size(key)  # Ciphertext-Groesse; App nutzt version.size_bytes
