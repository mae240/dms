# G-1: At-Rest-Verschlüsselung (Blobs) + Key-Rotation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dokument-Blobs (und Export-Dateien) werden transparent verschlüsselt at-rest gespeichert (AES-256-GCM). Ein **Keyring mit Versionen** erlaubt **Master-Key-Rotation ohne Neuverschlüsselung der Dateien** (nur die kleinen Data-Keys werden umgeschlüsselt). DSGVO Art. 32.

**Architecture:** Hybrid. Diese Datei deckt den **App-Level-Teil** ab: ein `EncryptedStorageBackend`-Decorator ver-/entschlüsselt streamend (gerahmtes AEAD, 64-KB-Frames) mit **Envelope-Verschlüsselung** — pro Blob ein zufälliger Data-Key (DEK), umschlossen mit einem Master-Key. Der **Header trägt eine Key-Versions-ID**: der Backend hält einen Keyring `{version: master_key}`, neue Writes nutzen die aktive Version, alte Blobs bleiben mit ihrer Version entschlüsselbar. Rotation = neue Version aktiv schalten + Blobs lazy/batch „re-wrappen" (DEK neu einwickeln, Datei-Body unverändert kopieren). Der **DB-Teil** (Postgres at-rest) läuft über Infrastruktur (verschlüsseltes Volume) und ist hier nur dokumentiert.

**Tech Stack:** Python 3.12, `cryptography` (AESGCM), `dms_core.storage`-Protocol, Pydantic-Settings, Celery (Re-Wrap-Task), pytest (`backend/tests`, kein DB-Fixture für die Krypto-Tests).

**Invarianten:** `file_hash` bleibt SHA-256 über den **Klartext** (Verschlüsselung am Storage-Layer transparent → Worker-Reverify bleibt grün). Streaming erhalten (keine 50-MB-Vollladung). Ohne Keyring = Verschlüsselung aus (Dev); in `production` Pflicht.

---

## File Structure

- **Create** `packages/dms_core/dms_core/storage/encrypted.py` — `EncryptedStorageBackend` (Keyring, Header mit Key-ID, `rewrap()`), gerahmtes AEAD, Reader-Adapter.
- **Modify** `packages/dms_core/dms_core/config.py` — Keyring-Settings + Parser + Prod-Pflicht.
- **Modify** `packages/dms_core/dms_core/storage/__init__.py` — Factory umhüllt Local mit Encrypted bei vorhandenem Keyring.
- **Modify** `packages/dms_core/pyproject.toml` — `cryptography`.
- **Modify** `packages/dms_core/dms_core/celery_app.py`, `worker/worker/tasks/maintenance.py` — `rewrap_blobs`-Task.
- **Modify** `backend/app/api/routes_admin.py` — Superadmin-Endpoint „Re-Wrap auslösen" (Rotations-Button).
- **Create** `backend/tests/test_storage_crypto.py` — Round-Trip, Tamper/Truncation, falscher Key, leer, **Rotation/Re-Wrap**.
- **Create** `scripts/reencrypt_blobs.py` — Bestands-Blobs erstmals verschlüsseln (Klartext → aktive Version).
- **Modify** `.env.example`, `Makefile`, `CLAUDE.md` — Keyring-Format, Key-Erzeugung, Rotations-Runbook, DB-Infra-Verschlüsselung.

**Header-Format (on disk):**
```
MAGIC            8 Bytes   b"DMSENC1\x00"
key_id           4 Bytes   big-endian uint -> welche Master-Key-Version den DEK wrappt
wrap_nonce      12 Bytes
wrapped_dek     48 Bytes   AESGCM(master[key_id]).encrypt(wrap_nonce, DEK[32], None)
dann je Frame:
  final          1 Byte    1 = letzter Frame  (authentifiziert via AAD)
  nonce         12 Bytes
  ct_len         4 Bytes   big-endian
  ct        ct_len Bytes   AESGCM(DEK).encrypt(nonce, plaintext_chunk, AAD)
AAD je Frame = struct.pack(">QB", frame_index, final)
```
Re-Wrap ändert nur MAGIC..wrapped_dek (neuer key_id + neu eingewickelter DEK); die Frames bleiben byte-identisch (DEK unverändert) → keine teure Datei-Neuverschlüsselung.

---

### Task 1: `cryptography`-Dependency

**Files:** Modify `packages/dms_core/pyproject.toml`

- [ ] **Step 1:** Unter `[project] dependencies` ergänzen: `"cryptography>=43,<46",`
- [ ] **Step 2:** Run: `docker compose build backend worker && docker compose run --rm --no-deps backend python -c "from cryptography.hazmat.primitives.ciphers.aead import AESGCM; print('ok')"` → Expected: `ok`
- [ ] **Step 3:** Commit: `git add packages/dms_core/pyproject.toml && git commit -m "G-1: cryptography-Dependency"`

---

### Task 2: Config — Keyring-Settings + Prod-Pflicht

**Files:** Modify `packages/dms_core/dms_core/config.py`; Test `backend/tests/test_config.py`

Keyring-Format in der Env (ein String, damit es ins bestehende `.env`-Modell passt):
`STORAGE_ENCRYPTION_KEYS="1:<base64-32B>,2:<base64-32B>"` und `STORAGE_ACTIVE_KEY_ID=2`.

- [ ] **Step 1: Failing tests** in `backend/tests/test_config.py`:

```python
def test_prod_requires_storage_keyring() -> None:
    with pytest.raises(ValueError, match="STORAGE_ENCRYPTION_KEYS"):
        _prod(storage_encryption_keys="", storage_active_key_id=0)


def test_prod_requires_active_key_in_ring() -> None:
    import base64

    key = base64.b64encode(b"\x00" * 32).decode()
    with pytest.raises(ValueError, match="STORAGE_ACTIVE_KEY_ID"):
        _prod(storage_encryption_keys=f"1:{key}", storage_active_key_id=9)


def test_keyring_parses() -> None:
    import base64

    k1 = base64.b64encode(b"\x01" * 32).decode()
    k2 = base64.b64encode(b"\x02" * 32).decode()
    s = Settings(storage_encryption_keys=f"1:{k1},2:{k2}", storage_active_key_id=2)
    ring = s.storage_keyring
    assert set(ring) == {1, 2}
    assert ring[2] == b"\x02" * 32
```

- [ ] **Step 2:** Run: `docker compose run --rm -w /app/backend backend pytest tests/test_config.py -q` → Expected: FAIL.

- [ ] **Step 3: Settings + Parser + Validierung** in `config.py`. Im Storage-Block:

```python
    # At-rest-Verschluesselung (Keyring). Format: "<id>:<base64-32B>,<id>:<base64-32B>".
    # Leer = aus (nur Dev). In production Pflicht. storage_active_key_id = Version fuer neue Writes.
    storage_encryption_keys: str = ""
    storage_active_key_id: int = 0
```

Property + Validator ergänzen:

```python
    @property
    def storage_keyring(self) -> dict[int, bytes]:
        import base64

        ring: dict[int, bytes] = {}
        for part in self.storage_encryption_keys.split(","):
            part = part.strip()
            if not part:
                continue
            sid, _, b64 = part.partition(":")
            key = base64.b64decode(b64, validate=True)
            if len(key) != 32:
                raise ValueError(f"Storage-Key {sid!r} ist nicht 32 Bytes")
            ring[int(sid)] = key
        return ring

    @model_validator(mode="after")
    def _enforce_storage_keyring(self) -> Settings:
        if self.environment == "production":
            if not self.storage_encryption_keys:
                raise ValueError(
                    "STORAGE_ENCRYPTION_KEYS muss in Produktion gesetzt sein (Art. 32)."
                )
            if self.storage_active_key_id not in self.storage_keyring:
                raise ValueError(
                    "STORAGE_ACTIVE_KEY_ID ist nicht im STORAGE_ENCRYPTION_KEYS-Ring enthalten."
                )
        return self
```

- [ ] **Step 4:** Run: `docker compose run --rm -w /app/backend backend pytest tests/test_config.py -q` → Expected: PASS.
- [ ] **Step 5:** Commit: `git add packages/dms_core/dms_core/config.py backend/tests/test_config.py && git commit -m "G-1: Keyring-Settings + Prod-Pflicht"`

---

### Task 3: `EncryptedStorageBackend` mit Keyring + Re-Wrap (Kernstück)

**Files:** Create `packages/dms_core/dms_core/storage/encrypted.py`; Test `backend/tests/test_storage_crypto.py`

- [ ] **Step 1: Failing tests** `backend/tests/test_storage_crypto.py`:

```python
"""Tests fuer EncryptedStorageBackend (gerahmtes AES-256-GCM, Keyring, Re-Wrap)."""

from __future__ import annotations

import io
import os

import pytest

from dms_core.storage.base import StorageError
from dms_core.storage.encrypted import _MAGIC, EncryptedStorageBackend


class _MemBackend:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def save(self, key: str, stream) -> str:  # noqa: ANN001
        self.blobs[key] = stream.read()
        return key

    def open_stream(self, key: str, *, chunk_size: int = 1024 * 1024):  # noqa: ANN001
        data = self.blobs[key]
        return iter(data[i : i + chunk_size] for i in range(0, len(data), chunk_size))

    def delete(self, key: str) -> None:
        self.blobs.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self.blobs

    def size(self, key: str) -> int:
        return len(self.blobs[key])


_RING = {1: b"\x01" * 32, 2: b"\x02" * 32}


def _backend(active: int = 1, ring=None) -> tuple[EncryptedStorageBackend, _MemBackend]:  # noqa: ANN001
    inner = _MemBackend()
    enc = EncryptedStorageBackend(inner, keyring=ring or {1: _RING[1]}, active_key_id=active)
    return enc, inner


def _read_all(it) -> bytes:  # noqa: ANN001
    return b"".join(it)


def test_roundtrip_multi_frame() -> None:
    enc, _ = _backend()
    payload = os.urandom(64 * 1024 * 3 + 17)
    enc.save("doc/v1", io.BytesIO(payload))
    assert _read_all(enc.open_stream("doc/v1")) == payload


def test_ciphertext_not_plaintext_and_has_header() -> None:
    enc, inner = _backend()
    enc.save("doc/v1", io.BytesIO(b"GEHEIM" * 100))
    assert inner.blobs["doc/v1"].startswith(_MAGIC)
    assert b"GEHEIM" not in inner.blobs["doc/v1"]


def test_empty_payload_roundtrips() -> None:
    enc, _ = _backend()
    enc.save("doc/v1", io.BytesIO(b""))
    assert _read_all(enc.open_stream("doc/v1")) == b""


def test_wrong_key_fails() -> None:
    enc, inner = _backend()
    enc.save("doc/v1", io.BytesIO(b"data"))
    other = EncryptedStorageBackend(inner, keyring={1: b"\x09" * 32}, active_key_id=1)
    with pytest.raises(StorageError):
        _read_all(other.open_stream("doc/v1"))


def test_tampered_ciphertext_fails() -> None:
    enc, inner = _backend()
    enc.save("doc/v1", io.BytesIO(b"unveraenderbar"))
    blob = bytearray(inner.blobs["doc/v1"])
    blob[-1] ^= 0xFF
    inner.blobs["doc/v1"] = bytes(blob)
    with pytest.raises(StorageError):
        _read_all(enc.open_stream("doc/v1"))


def test_truncated_blob_fails() -> None:
    enc, inner = _backend()
    enc.save("doc/v1", io.BytesIO(os.urandom(64 * 1024 * 2)))
    inner.blobs["doc/v1"] = inner.blobs["doc/v1"][:-100]
    with pytest.raises(StorageError):
        _read_all(enc.open_stream("doc/v1"))


def test_bad_key_length_rejected() -> None:
    with pytest.raises(ValueError, match="32 Bytes"):
        EncryptedStorageBackend(_MemBackend(), keyring={1: b"kurz"}, active_key_id=1)


def test_active_key_must_be_in_ring() -> None:
    with pytest.raises(ValueError, match="aktive Key-Version"):
        EncryptedStorageBackend(_MemBackend(), keyring={1: _RING[1]}, active_key_id=2)


# ---- Rotation / Re-Wrap ----

def test_rewrap_migrates_to_active_key_and_preserves_content() -> None:
    payload = os.urandom(64 * 1024 + 5)
    inner = _MemBackend()
    # mit Version 1 schreiben
    EncryptedStorageBackend(inner, keyring={1: _RING[1]}, active_key_id=1).save(
        "doc/v1", io.BytesIO(payload)
    )
    # Backend mit beiden Keys, aktiv = 2
    enc = EncryptedStorageBackend(inner, keyring=_RING, active_key_id=2)
    assert _read_all(enc.open_stream("doc/v1")) == payload  # altes Blob noch lesbar
    assert enc.rewrap("doc/v1") is True  # auf Version 2 umgeschluesselt
    assert _read_all(enc.open_stream("doc/v1")) == payload  # Inhalt unveraendert
    # erneuter Re-Wrap = no-op (schon aktiv)
    assert enc.rewrap("doc/v1") is False


def test_rewrap_unknown_version_fails() -> None:
    inner = _MemBackend()
    EncryptedStorageBackend(inner, keyring={1: _RING[1]}, active_key_id=1).save(
        "doc/v1", io.BytesIO(b"x")
    )
    enc = EncryptedStorageBackend(inner, keyring={2: _RING[2]}, active_key_id=2)
    with pytest.raises(StorageError, match="Key-Version"):
        enc.rewrap("doc/v1")
```

- [ ] **Step 2:** Run: `docker compose run --rm -w /app/backend backend pytest tests/test_storage_crypto.py -q` → Expected: FAIL (Modul fehlt).

- [ ] **Step 3: `encrypted.py` implementieren:**

```python
"""Transparente At-rest-Verschluesselung als StorageBackend-Decorator.

Gerahmtes AES-256-GCM (64-KB-Frames) mit Envelope-Verschluesselung: pro Blob ein
zufaelliger Data-Key (DEK), umschlossen mit einem Master-Key aus dem Keyring.
Der Header traegt die Key-Versions-ID -> Rotation ohne Datei-Neuverschluesselung
(rewrap() schluesselt nur den DEK um). Streamend; AAD bindet Frame-Index + Ende.
"""

from __future__ import annotations

import os
import struct
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
        yield _MAGIC + _KEYID.pack(self._active) + wrap_nonce + self._active_aes.encrypt(
            wrap_nonce, dek, None
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
            raise StorageError("DEK-Entschluesselung fehlgeschlagen (falscher Master-Key?)") from exc

    def _decrypt(self, it: Iterator[bytes]) -> Iterator[bytes]:
        r = _FrameReader(it)
        dek = self._read_header(r)
        aes = AESGCM(dek)
        index = 0
        while True:
            (final,) = _HDR.unpack(r.read_exact(1))
            nonce = r.read_exact(_NONCE)
            (clen,) = _LEN.unpack(r.read_exact(_LEN.size))
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
            _MAGIC + _KEYID.pack(self._active) + new_nonce + self._active_aes.encrypt(
                new_nonce, dek, None
            )
        )

        def _body() -> Iterator[bytes]:
            yield new_header
            yield from r.drain()  # restliche Frames unveraendert

        self._inner.save(key, _IterReader(_body()))
        return True

    # ---- Pass-through ----

    def delete(self, key: str) -> None:
        self._inner.delete(key)

    def exists(self, key: str) -> bool:
        return self._inner.exists(key)

    def size(self, key: str) -> int:
        return self._inner.size(key)  # Ciphertext-Groesse; App nutzt version.size_bytes
```

- [ ] **Step 4:** Run: `docker compose run --rm -w /app/backend backend pytest tests/test_storage_crypto.py -q` → Expected: PASS (alle, inkl. Rotation).
- [ ] **Step 5:** Ruff + Commit:

```bash
mise x ruff@0.8.4 -- ruff check packages/dms_core/dms_core/storage/encrypted.py backend/tests/test_storage_crypto.py
git add packages/dms_core/dms_core/storage/encrypted.py backend/tests/test_storage_crypto.py
git commit -m "G-1: EncryptedStorageBackend mit Keyring + rewrap()"
```

---

### Task 4: Factory verdrahten

**Files:** Modify `packages/dms_core/dms_core/storage/__init__.py`; Test `backend/tests/test_storage_crypto.py`

- [ ] **Step 1: Failing tests** ergänzen:

```python
def test_factory_wraps_when_keyring_set(monkeypatch) -> None:  # noqa: ANN001
    import base64

    from dms_core import storage as storage_mod
    from dms_core.config import settings

    storage_mod.get_storage.cache_clear()
    key = base64.b64encode(b"\x05" * 32).decode()
    monkeypatch.setattr(settings, "storage_encryption_keys", f"1:{key}")
    monkeypatch.setattr(settings, "storage_active_key_id", 1)
    backend = storage_mod.get_storage()
    storage_mod.get_storage.cache_clear()
    assert isinstance(backend, EncryptedStorageBackend)


def test_factory_plain_when_no_keyring(monkeypatch) -> None:  # noqa: ANN001
    from dms_core import storage as storage_mod
    from dms_core.config import settings
    from dms_core.storage.local import LocalFilesystemBackend

    storage_mod.get_storage.cache_clear()
    monkeypatch.setattr(settings, "storage_encryption_keys", "")
    backend = storage_mod.get_storage()
    storage_mod.get_storage.cache_clear()
    assert isinstance(backend, LocalFilesystemBackend)
```

- [ ] **Step 2:** Run: `... pytest tests/test_storage_crypto.py -q -k factory` → Expected: FAIL.

- [ ] **Step 3: Factory** in `storage/__init__.py`:

```python
from dms_core.storage.encrypted import EncryptedStorageBackend


def _maybe_encrypt(backend: StorageBackend) -> StorageBackend:
    ring = settings.storage_keyring
    if ring:
        return EncryptedStorageBackend(
            backend, keyring=ring, active_key_id=settings.storage_active_key_id
        )
    return backend
```

`get_storage` und `get_export_storage` jeweils `return _maybe_encrypt(LocalFilesystemBackend(...))`.

- [ ] **Step 4:** Run: `... pytest tests/test_storage_crypto.py -q && make test && make test-worker` → Expected: PASS (bestehende Upload-/Download-/Worker-Tests grün → Transparenz + Klartext-`file_hash` bestätigt).
- [ ] **Step 5:** Commit: `git add packages/dms_core/dms_core/storage/__init__.py backend/tests/test_storage_crypto.py && git commit -m "G-1: Factory umhuellt Local mit Encrypted bei vorhandenem Keyring"`

---

### Task 5: Bestands-Blobs erstmals verschlüsseln (Script)

**Files:** Create `scripts/reencrypt_blobs.py`

Bestehende Klartext-Blobs müssen einmalig in das verschlüsselte Format (aktive Version). Idempotent: Blobs mit `DMSENC1`-Header werden übersprungen.

- [ ] **Step 1:** `scripts/reencrypt_blobs.py`:

```python
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
from dms_core.storage.encrypted import _MAGIC, EncryptedStorageBackend
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
```

- [ ] **Step 2:** Verifizieren (Dev-Keyring in `.env`, dann): `docker compose run --rm backend python -m app.seed && docker compose run --rm backend python /app/scripts/reencrypt_blobs.py && make test` → Expected: „N verschluesselt"; Download/Tests weiterhin korrekt.
- [ ] **Step 3:** Commit: `git add scripts/reencrypt_blobs.py && git commit -m "G-1: Einmal-Script — Bestands-Blobs verschluesseln"`

---

### Task 6: Rotations-Button — Re-Wrap-Task + Superadmin-Endpoint

**Files:** Modify `packages/dms_core/dms_core/celery_app.py`, `worker/worker/tasks/maintenance.py`, `backend/app/api/routes_admin.py`; Test `backend/tests/test_compliance.py` (Endpoint-Auth)

Ablauf einer Rotation (Runbook in Task 7 dokumentiert):
1. Ops: neue Key-Version erzeugen, zu `STORAGE_ENCRYPTION_KEYS` hinzufügen, `STORAGE_ACTIVE_KEY_ID` auf die neue Version setzen, Dienste neu starten. (Neue Uploads nutzen ab jetzt die neue Version; alte Blobs bleiben mit ihrer alten Version lesbar, solange diese im Ring bleibt.)
2. **Button:** Superadmin löst Re-Wrap aus → Hintergrund-Task schlüsselt alle Blobs ≠ aktive Version auf die aktive Version um (nur DEK, kein Datei-Re-Encrypt).
3. Ops: sobald der Re-Wrap durch ist, die alte Key-Version aus `STORAGE_ENCRYPTION_KEYS` entfernen.

- [ ] **Step 1:** In `celery_app.py` Task-Name + Route ergänzen (kein Beat — wird per Button getriggert):

```python
TASK_REWRAP_BLOBS = "tasks.rewrap_blobs"
```
in `task_routes`: `TASK_REWRAP_BLOBS: {"queue": "maintenance"},`

- [ ] **Step 2: Re-Wrap-Kernlogik** in `dms_core/maintenance.py`:

```python
def rewrap_blobs(session: Session, storage: object) -> dict[str, int]:
    """Schluesselt alle Blobs auf die aktive Key-Version um. `storage` muss
    rewrap(key)->bool unterstuetzen (EncryptedStorageBackend). Idempotent."""
    if not hasattr(storage, "rewrap"):
        return {"rewrapped": 0, "skipped": 0, "errors": 0}
    keys = [v.storage_key for v in session.exec(select(DocumentVersion)).all()]
    rewrapped = skipped = errors = 0
    for key in keys:
        try:
            if storage.rewrap(key):
                rewrapped += 1
            else:
                skipped += 1
        except StorageError:
            errors += 1  # einzelner Blob blockiert die Rotation nicht
    return {"rewrapped": rewrapped, "skipped": skipped, "errors": errors}
```

(`StorageError` ist in `maintenance.py` bereits importiert; sonst ergänzen.)

- [ ] **Step 3: Worker-Wrapper** in `worker/worker/tasks/maintenance.py`:

```python
@celery_app.task(name=TASK_REWRAP_BLOBS)
def rewrap_blobs() -> dict:
    with session_scope() as session:
        return maintenance.rewrap_blobs(session, get_storage())
```
(Import `TASK_REWRAP_BLOBS` ergänzen.)

- [ ] **Step 4: Endpoint** in `routes_admin.py` (Superadmin), enqueued den Task:

```python
@router.post("/storage/rewrap", status_code=status.HTTP_202_ACCEPTED)
def trigger_rewrap(_: SuperadminDep, request: Request) -> dict:
    from dms_core.celery_app import TASK_REWRAP_BLOBS, celery_app

    celery_app.send_task(TASK_REWRAP_BLOBS)
    return {"status": "enqueued"}
```

- [ ] **Step 5: Failing/passing Auth-Test** in `backend/tests/test_compliance.py`:

```python
def test_rewrap_requires_superadmin(client, editor_headers):  # noqa: ANN001
    res = client.post("/api/admin/storage/rewrap", headers=editor_headers)
    assert res.status_code == 403
```
(Enqueue im Test ist via `_no_enqueue`-Fixture nicht betroffen; ggf. `celery_app.send_task` analog mocken, falls der Test es real triggert — Muster aus den bestehenden Admin-Tests übernehmen.)

- [ ] **Step 6:** Run: `make test && make test-worker` → Expected: PASS.
- [ ] **Step 7:** Commit: `git add packages/dms_core/dms_core/celery_app.py worker/worker/tasks/maintenance.py backend/app/api/routes_admin.py packages/dms_core/dms_core/maintenance.py backend/tests/test_compliance.py && git commit -m "G-1: Rotations-Button — Re-Wrap-Task + Superadmin-Endpoint"`

---

### Task 7: Doku — Keyring, Key-Erzeugung, Rotations-Runbook, DB-Infra

**Files:** Modify `.env.example`, `Makefile`, `CLAUDE.md`

- [ ] **Step 1: `.env.example`:**

```bash
# At-rest-Verschluesselung (Keyring). Format: "<id>:<base64-32B>,<id>:<base64-32B>"
# Key erzeugen: make gen-storage-key
# In Produktion PFLICHT. Key-Verlust = Totalverlust aller Dokumente -> KMS/Passwortsafe.
STORAGE_ENCRYPTION_KEYS=
STORAGE_ACTIVE_KEY_ID=1
```

- [ ] **Step 2: Make-Target:**

```makefile
gen-storage-key: ## Erzeugt einen Storage-Master-Key (Base64, 32 Byte)
	@python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
```

- [ ] **Step 3: CLAUDE.md** — unter „Sicherheit": At-rest-Verschlüsselung der Blobs bei gesetztem Keyring (Prod-Pflicht). **Rotations-Runbook:** (1) `make gen-storage-key` → neue Version mit höherer ID in `STORAGE_ENCRYPTION_KEYS` ergänzen, `STORAGE_ACTIVE_KEY_ID` hochsetzen, Dienste neu starten; (2) Superadmin → `POST /api/admin/storage/rewrap` (Button) auslösen; (3) nach Abschluss die alte Key-Version aus dem Ring entfernen. **DB-at-rest separat über verschlüsseltes Volume (LUKS/verschlüsseltes Hetzner-Volume)** für Postgres-Datenverzeichnis + Storage-Mount.

- [ ] **Step 4:** Commit: `git add .env.example Makefile CLAUDE.md && git commit -m "G-1: Doku — Keyring, Key-Erzeugung, Rotations-Runbook, DB-Infra"`

---

## Self-Review

- **Spec-Abdeckung:** App-Level-Blob-Verschlüsselung (Task 3/4), Keyring + Key aus Env (Task 2/3), Bestands-Migration (Task 5), **Key-Rotation ohne Datei-Re-Encrypt via `rewrap()` + Button** (Task 6), DB-Infra dokumentiert (Task 7). ✓
- **Invarianten:** `file_hash` bleibt Klartext-Hash (Task 4 beweist via grüner Upload/Worker-Suite); Streaming erhalten; Re-Wrap kopiert Frames unverändert (kein 50-MB-Re-Encrypt). ✓
- **Type-Konsistenz:** `EncryptedStorageBackend(inner, *, keyring, active_key_id)` einheitlich; `rewrap(key)->bool` in Krypto (Task 3) und Maintenance (Task 6). ✓
- **Restrisiko (dokumentiert):** Key-Erzeugung/Ring-Update sind Ops-Schritte (Env + Neustart); der Button migriert nur die Blobs. Beim Entfernen einer alten Version vorher sicherstellen, dass kein Blob mehr darauf zeigt (Re-Wrap mit `errors=0` durchgelaufen).

---

## Execution Handoff

1. **Subagent-Driven (empfohlen)** — pro Task ein frischer Subagent, Review dazwischen.
2. **Inline** — Tasks in dieser Session mit Checkpoints.
