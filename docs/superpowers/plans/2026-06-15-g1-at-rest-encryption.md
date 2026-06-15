# G-1: At-Rest-Verschlüsselung (Blobs) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dokument-Blobs (und Export-Dateien) werden transparent verschlüsselt at-rest gespeichert (AES-256-GCM), sodass ein Diebstahl der Platte/des Backups/des Storage-Mounts ohne Schlüssel wertlos ist (DSGVO Art. 32).

**Architecture:** Hybrid-Ansatz. Diese Plan-Datei deckt den **App-Level-Teil** ab: ein `EncryptedStorageBackend`-Decorator umschließt das bestehende `StorageBackend`-Protocol und ver-/entschlüsselt streamend (gerahmtes AEAD, 64 KB-Frames). Envelope-Verschlüsselung: pro Blob ein zufälliger Data-Key (DEK), umschlossen mit einem Master-Key aus der Umgebung. Der **DB-Teil** (Postgres at-rest) wird über Infrastruktur (verschlüsseltes Volume) gelöst und ist hier nur dokumentiert, kein Code.

**Tech Stack:** Python 3.12, `cryptography` (AESGCM), bestehendes `dms_core.storage`-Protocol, Pydantic-Settings, pytest (in `backend/tests`, kein DB-Fixture nötig).

**Wichtige Invarianten (nicht brechen):**
- `file_hash` bleibt der SHA-256 über den **Klartext** (Upload hasht vor Verschlüsselung; Worker entschlüsselt beim Lesen und hasht Klartext → Reverify bleibt grün).
- Die Verschlüsselung ist **am Storage-Layer transparent**: Services/Worker sehen weiter nur `save(stream)` / `open_stream(key)`.
- Streaming bleibt erhalten (keine 50-MB-Vollladung in den Heap).
- Bei leerem/fehlendem `storage_encryption_key` ist die Verschlüsselung **aus** (Dev-Default), in `production` **Pflicht**.

---

## File Structure

- **Create** `packages/dms_core/dms_core/storage/encrypted.py` — `EncryptedStorageBackend` + gerahmtes AEAD + Reader-Adapter. Eine Verantwortung: transparente Blob-Verschlüsselung.
- **Modify** `packages/dms_core/dms_core/config.py` — Setting `storage_encryption_key`; Prod-Pflicht im Validator.
- **Modify** `packages/dms_core/dms_core/storage/__init__.py` — Factory umhüllt Local mit Encrypted, wenn Key gesetzt.
- **Modify** `packages/dms_core/pyproject.toml` — Dependency `cryptography`.
- **Create** `backend/tests/test_storage_crypto.py` — Round-Trip, Tamper-/Truncation-Erkennung, falscher Key, leerer Input, Streaming-Größe.
- **Create** `scripts/reencrypt_blobs.py` — Einmal-Migration bestehender Klartext-Blobs → verschlüsselt.
- **Modify** `.env.example`, `Makefile`, `README.md`/`CLAUDE.md` — Key-Erzeugung dokumentieren, DB-Infra-Verschlüsselung als Betriebsanweisung.

---

### Task 1: `cryptography`-Dependency ergänzen

**Files:**
- Modify: `packages/dms_core/pyproject.toml`

- [ ] **Step 1: Dependency eintragen**

In `packages/dms_core/pyproject.toml` unter `[project] dependencies` ergänzen (Stil der vorhandenen Einträge):

```toml
    "cryptography>=43,<46",
```

- [ ] **Step 2: Image neu bauen, Import prüfen**

Run: `docker compose build backend worker && docker compose run --rm --no-deps backend python -c "from cryptography.hazmat.primitives.ciphers.aead import AESGCM; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add packages/dms_core/pyproject.toml
git commit -m "G-1: cryptography-Dependency fuer At-rest-Verschluesselung"
```

---

### Task 2: Config — `storage_encryption_key` + Prod-Pflicht

**Files:**
- Modify: `packages/dms_core/dms_core/config.py:45-48` (Storage-Block) und `:86-98` (`_enforce_prod_secrets`)
- Test: `backend/tests/test_config.py` (bestehende Datei erweitern)

- [ ] **Step 1: Failing test schreiben**

In `backend/tests/test_config.py` ergänzen:

```python
def test_prod_requires_storage_encryption_key() -> None:
    with pytest.raises(ValueError, match="STORAGE_ENCRYPTION_KEY"):
        _prod(storage_encryption_key="")


def test_prod_accepts_valid_storage_key() -> None:
    import base64

    key = base64.b64encode(b"\x00" * 32).decode()
    settings = _prod(storage_encryption_key=key)
    assert settings.storage_encryption_key == key
```

- [ ] **Step 2: Test laufen lassen (muss fehlschlagen)**

Run: `docker compose run --rm -w /app/backend backend pytest tests/test_config.py -q`
Expected: FAIL (`test_prod_requires_storage_encryption_key` — kein Setting / keine Validierung).

- [ ] **Step 3: Setting + Validierung implementieren**

In `config.py` im Storage-Block (nach `export_root`) ergänzen:

```python
    # At-rest-Verschluesselung der Blobs (Base64-kodierter 32-Byte-Master-Key).
    # Leer = aus (nur Dev). In production Pflicht (siehe _enforce_prod_secrets).
    storage_encryption_key: str = ""
```

In `_enforce_prod_secrets` vor `return self` ergänzen:

```python
        if self.environment == "production" and not self.storage_encryption_key:
            raise ValueError(
                "STORAGE_ENCRYPTION_KEY muss in Produktion gesetzt sein "
                "(At-rest-Verschluesselung der Dokumente, Art. 32)."
            )
```

- [ ] **Step 4: Test laufen lassen (muss bestehen)**

Run: `docker compose run --rm -w /app/backend backend pytest tests/test_config.py -q`
Expected: PASS (alle Config-Tests).

- [ ] **Step 5: Commit**

```bash
git add packages/dms_core/dms_core/config.py backend/tests/test_config.py
git commit -m "G-1: storage_encryption_key Setting + Prod-Pflicht"
```

---

### Task 3: `EncryptedStorageBackend` — gerahmtes AEAD (Kernstück)

**Files:**
- Create: `packages/dms_core/dms_core/storage/encrypted.py`
- Test: `backend/tests/test_storage_crypto.py`

**Frame-Format (on disk):**
```
MAGIC            8 Bytes   b"DMSENC1\x00"
wrap_nonce      12 Bytes   Nonce fuer DEK-Wrapping
wrapped_dek     48 Bytes   AESGCM(master).encrypt(nonce, DEK[32], None)  -> 32+16
dann je Frame:
  final          1 Byte    1 = letzter Frame, sonst 0  (authentifiziert via AAD)
  nonce         12 Bytes   pro Frame zufaellig
  ct_len         4 Bytes   big-endian Laenge des Ciphertext (= Klartext + 16 Tag)
  ct        ct_len Bytes   AESGCM(DEK).encrypt(nonce, plaintext_chunk, AAD)
AAD je Frame = struct.pack(">QB", frame_index, final)
```
Schutz: Master-Key wrappt DEK; AAD bindet Reihenfolge (`frame_index`) und Ende (`final`) → Truncation/Reordering/Flag-Manipulation werden beim Entschlüsseln erkannt.

- [ ] **Step 1: Failing tests schreiben**

`backend/tests/test_storage_crypto.py`:

```python
"""Tests fuer EncryptedStorageBackend (gerahmtes AES-256-GCM, kein DB-Fixture noetig)."""

from __future__ import annotations

import io
import os

import pytest

from dms_core.storage.base import StorageError
from dms_core.storage.encrypted import EncryptedStorageBackend


class _MemBackend:
    """Minimaler In-Memory-StorageBackend fuer Tests."""

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


def _backend() -> tuple[EncryptedStorageBackend, _MemBackend]:
    inner = _MemBackend()
    enc = EncryptedStorageBackend(inner, master_key=b"\x01" * 32)
    return enc, inner


def _read_all(it) -> bytes:  # noqa: ANN001
    return b"".join(it)


def test_roundtrip_small() -> None:
    enc, _ = _backend()
    payload = b"Vertraulicher Vertragstext"
    enc.save("doc/v1", io.BytesIO(payload))
    assert _read_all(enc.open_stream("doc/v1")) == payload


def test_roundtrip_multi_frame() -> None:
    enc, _ = _backend()
    payload = os.urandom(64 * 1024 * 3 + 17)  # > 3 Frames, krumm
    enc.save("doc/v1", io.BytesIO(payload))
    assert _read_all(enc.open_stream("doc/v1")) == payload


def test_ciphertext_is_not_plaintext() -> None:
    enc, inner = _backend()
    payload = b"GEHEIM" * 100
    enc.save("doc/v1", io.BytesIO(payload))
    assert payload not in inner.blobs["doc/v1"]
    assert inner.blobs["doc/v1"].startswith(b"DMSENC1\x00")


def test_empty_payload_roundtrips() -> None:
    enc, _ = _backend()
    enc.save("doc/v1", io.BytesIO(b""))
    assert _read_all(enc.open_stream("doc/v1")) == b""


def test_wrong_master_key_fails() -> None:
    enc, inner = _backend()
    enc.save("doc/v1", io.BytesIO(b"data"))
    other = EncryptedStorageBackend(inner, master_key=b"\x02" * 32)
    with pytest.raises(StorageError):
        _read_all(other.open_stream("doc/v1"))


def test_tampered_ciphertext_fails() -> None:
    enc, inner = _backend()
    enc.save("doc/v1", io.BytesIO(b"data-die-nicht-veraendert-werden-darf"))
    blob = bytearray(inner.blobs["doc/v1"])
    blob[-1] ^= 0xFF  # letztes Byte kippen
    inner.blobs["doc/v1"] = bytes(blob)
    with pytest.raises(StorageError):
        _read_all(enc.open_stream("doc/v1"))


def test_truncated_blob_fails() -> None:
    enc, inner = _backend()
    enc.save("doc/v1", io.BytesIO(os.urandom(64 * 1024 * 2)))
    inner.blobs["doc/v1"] = inner.blobs["doc/v1"][:-100]  # finaler Frame fehlt/kaputt
    with pytest.raises(StorageError):
        _read_all(enc.open_stream("doc/v1"))


def test_bad_master_key_length_rejected() -> None:
    with pytest.raises(ValueError, match="32 Bytes"):
        EncryptedStorageBackend(_MemBackend(), master_key=b"zu-kurz")
```

- [ ] **Step 2: Tests laufen lassen (müssen fehlschlagen)**

Run: `docker compose run --rm -w /app/backend backend pytest tests/test_storage_crypto.py -q`
Expected: FAIL (`ModuleNotFoundError: dms_core.storage.encrypted`).

- [ ] **Step 3: `encrypted.py` implementieren**

`packages/dms_core/dms_core/storage/encrypted.py`:

```python
"""Transparente At-rest-Verschluesselung als StorageBackend-Decorator.

Gerahmtes AES-256-GCM (64-KB-Frames) mit Envelope-Verschluesselung: pro Blob
ein zufaelliger Data-Key (DEK), umschlossen mit einem Master-Key. Streamend —
nie liegt die ganze Datei als bytes im Heap. AAD bindet Frame-Index und das
Ende-Flag und schuetzt so vor Truncation/Reordering.
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
_FRAME = 64 * 1024  # Klartext-Chunkgroesse pro Frame
_NONCE = 12
_WRAPPED_DEK = 48  # 32-Byte-DEK + 16-Byte-Tag
_AAD = struct.Struct(">QB")  # (frame_index, final)
_HDR = struct.Struct(">B")  # final-Flag im Frame-Header
_LEN = struct.Struct(">I")  # Ciphertext-Laenge


class _IterReader:
    """Adaptiert einen Byte-Iterator zu einem .read(n)-faehigen Objekt (fuer save())."""

    def __init__(self, it: Iterator[bytes]) -> None:
        self._it = it
        self._buf = bytearray()
        self._eof = False

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            rest = b"".join(self._it)
            out = bytes(self._buf) + rest
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


class EncryptedStorageBackend:
    """Umschliesst ein StorageBackend und ver-/entschluesselt Blobs transparent."""

    def __init__(self, inner: StorageBackend, *, master_key: bytes) -> None:
        if len(master_key) != 32:
            raise ValueError("master_key muss genau 32 Bytes (256 Bit) sein")
        self._inner = inner
        self._master = AESGCM(master_key)

    # ---- Schreiben ----

    def _encrypt(self, plaintext: BinaryIO) -> Iterator[bytes]:
        dek = AESGCM.generate_key(bit_length=256)
        aes = AESGCM(dek)
        wrap_nonce = os.urandom(_NONCE)
        yield _MAGIC + wrap_nonce + self._master.encrypt(wrap_nonce, dek, None)

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

    def _decrypt(self, it: Iterator[bytes]) -> Iterator[bytes]:
        r = _FrameReader(it)
        if r.read_exact(len(_MAGIC)) != _MAGIC:
            raise StorageError("Kein gueltiger DMS-Verschluesselungs-Header")
        wrap_nonce = r.read_exact(_NONCE)
        wrapped = r.read_exact(_WRAPPED_DEK)
        try:
            dek = self._master.decrypt(wrap_nonce, wrapped, None)
        except InvalidTag as exc:
            raise StorageError("DEK-Entschluesselung fehlgeschlagen (falscher Master-Key?)") from exc
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

    # ---- Pass-through ----

    def delete(self, key: str) -> None:
        self._inner.delete(key)

    def exists(self, key: str) -> bool:
        return self._inner.exists(key)

    def size(self, key: str) -> int:
        # Hinweis: liefert die CIPHERTEXT-Groesse. Fuer die Klartext-Groesse die
        # gespeicherte version.size_bytes verwenden.
        return self._inner.size(key)
```

- [ ] **Step 4: Tests laufen lassen (müssen bestehen)**

Run: `docker compose run --rm -w /app/backend backend pytest tests/test_storage_crypto.py -q`
Expected: PASS (alle 8 Tests).

- [ ] **Step 5: Ruff + Commit**

```bash
mise x ruff@0.8.4 -- ruff check packages/dms_core/dms_core/storage/encrypted.py backend/tests/test_storage_crypto.py
git add packages/dms_core/dms_core/storage/encrypted.py backend/tests/test_storage_crypto.py
git commit -m "G-1: EncryptedStorageBackend (gerahmtes AES-256-GCM, Envelope)"
```

---

### Task 4: Factory verdrahten

**Files:**
- Modify: `packages/dms_core/dms_core/storage/__init__.py`
- Test: `backend/tests/test_storage_crypto.py` (ergänzen)

- [ ] **Step 1: Failing test schreiben**

In `backend/tests/test_storage_crypto.py` ergänzen:

```python
def test_factory_wraps_when_key_set(monkeypatch) -> None:  # noqa: ANN001
    import base64

    from dms_core import storage as storage_mod
    from dms_core.config import settings

    storage_mod.get_storage.cache_clear()
    monkeypatch.setattr(settings, "storage_encryption_key", base64.b64encode(b"\x03" * 32).decode())
    backend = storage_mod.get_storage()
    storage_mod.get_storage.cache_clear()
    assert isinstance(backend, EncryptedStorageBackend)


def test_factory_plain_when_no_key(monkeypatch) -> None:  # noqa: ANN001
    from dms_core import storage as storage_mod
    from dms_core.config import settings
    from dms_core.storage.local import LocalFilesystemBackend

    storage_mod.get_storage.cache_clear()
    monkeypatch.setattr(settings, "storage_encryption_key", "")
    backend = storage_mod.get_storage()
    storage_mod.get_storage.cache_clear()
    assert isinstance(backend, LocalFilesystemBackend)
```

- [ ] **Step 2: Tests laufen lassen (müssen fehlschlagen)**

Run: `docker compose run --rm -w /app/backend backend pytest tests/test_storage_crypto.py -q -k factory`
Expected: FAIL (Factory umhüllt noch nicht).

- [ ] **Step 3: Factory + Key-Loader implementieren**

In `packages/dms_core/dms_core/storage/__init__.py` ergänzen:

```python
import base64

from dms_core.storage.base import StorageError
from dms_core.storage.encrypted import EncryptedStorageBackend


def _load_master_key() -> bytes:
    raw = settings.storage_encryption_key
    try:
        key = base64.b64decode(raw, validate=True)
    except (ValueError, TypeError) as exc:
        raise StorageError("STORAGE_ENCRYPTION_KEY ist kein gueltiges Base64") from exc
    if len(key) != 32:
        raise StorageError("STORAGE_ENCRYPTION_KEY muss 32 Bytes (Base64) sein")
    return key


def _maybe_encrypt(backend: StorageBackend) -> StorageBackend:
    if settings.storage_encryption_key:
        return EncryptedStorageBackend(backend, master_key=_load_master_key())
    return backend
```

`get_storage` und `get_export_storage` jeweils auf `return _maybe_encrypt(LocalFilesystemBackend(...))` umstellen. (Export-Dateien enthalten PII → ebenfalls verschlüsseln.)

- [ ] **Step 4: Tests + ganze Suite**

Run: `docker compose run --rm -w /app/backend backend pytest tests/test_storage_crypto.py -q && make test && make test-worker`
Expected: PASS — auch die bestehenden Upload-/Download-/Worker-Tests (Transparenz bestätigt: `file_hash`-Reverify im Worker bleibt grün, weil Klartext gehasht wird).

- [ ] **Step 5: Commit**

```bash
git add packages/dms_core/dms_core/storage/__init__.py backend/tests/test_storage_crypto.py
git commit -m "G-1: Storage-Factory umhuellt Local mit Encrypted bei gesetztem Key"
```

---

### Task 5: Re-Encrypt-Script für Bestands-Blobs

**Files:**
- Create: `scripts/reencrypt_blobs.py`

Bestehende Blobs sind Klartext; nach Aktivierung der Verschlüsselung würde `open_stream` sie nicht mehr entschlüsseln können. Dieses Einmal-Script liest jeden Blob roh (unverschlüsselt) und schreibt ihn verschlüsselt zurück. Idempotent: bereits verschlüsselte Blobs (Magic-Header) werden übersprungen.

- [ ] **Step 1: Script implementieren**

`scripts/reencrypt_blobs.py`:

```python
"""Einmal-Migration: bestehende Klartext-Blobs at-rest verschluesseln.

Idempotent: Blobs mit gueltigem DMSENC1-Header werden uebersprungen.
Lauf NACH dem Setzen von STORAGE_ENCRYPTION_KEY, im backend-Container:
    docker compose run --rm backend python /app/scripts/reencrypt_blobs.py
"""

from __future__ import annotations

import io
import sys

from sqlmodel import Session, select

from dms_core.config import settings
from dms_core.db import engine
from dms_core.models.document import DocumentVersion
from dms_core.storage import _load_master_key
from dms_core.storage.encrypted import _MAGIC, EncryptedStorageBackend
from dms_core.storage.local import LocalFilesystemBackend


def main() -> int:
    if not settings.storage_encryption_key:
        print("STORAGE_ENCRYPTION_KEY nicht gesetzt — nichts zu tun.")
        return 1
    raw = LocalFilesystemBackend(settings.storage_root)
    enc = EncryptedStorageBackend(raw, master_key=_load_master_key())

    migrated = skipped = 0
    with Session(engine) as session:
        keys = [v.storage_key for v in session.exec(select(DocumentVersion)).all()]
    for key in keys:
        if not raw.exists(key):
            continue
        head = b"".join(raw.open_stream(key, chunk_size=len(_MAGIC)))[: len(_MAGIC)]
        if head == _MAGIC:
            skipped += 1
            continue
        plaintext = b"".join(raw.open_stream(key))
        enc.save(key, io.BytesIO(plaintext))  # ueberschreibt atomar (os.replace)
        migrated += 1
    print(f"Fertig: {migrated} verschluesselt, {skipped} bereits verschluesselt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Trockenlauf gegen Dev-Daten verifizieren**

Run (Dev-Key in `.env` setzen, dann):
`docker compose run --rm backend python -m app.seed && docker compose run --rm backend python /app/scripts/reencrypt_blobs.py && make test`
Expected: Script meldet „N verschluesselt"; danach Download im UI/Tests weiterhin korrekt (Klartext zurück).

- [ ] **Step 3: Commit**

```bash
git add scripts/reencrypt_blobs.py
git commit -m "G-1: Einmal-Script zum Verschluesseln bestehender Blobs"
```

---

### Task 6: Doku — Key-Erzeugung, .env, DB-Infra-Verschlüsselung

**Files:**
- Modify: `.env.example`, `Makefile`, `CLAUDE.md`

- [ ] **Step 1: `.env.example` ergänzen**

```bash
# At-rest-Verschluesselung der Blobs (Base64-kodierter 32-Byte-Key).
# Erzeugen: make gen-storage-key   (oder: python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())")
# In Produktion PFLICHT. Verlust des Keys = Totalverlust aller Dokumente -> sicher hinterlegen (KMS/Passwortsafe).
STORAGE_ENCRYPTION_KEY=
```

- [ ] **Step 2: Make-Target für Key-Erzeugung**

In `Makefile`:

```makefile
gen-storage-key: ## Erzeugt einen STORAGE_ENCRYPTION_KEY (Base64, 32 Byte)
	@python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
```

- [ ] **Step 3: CLAUDE.md — Security-Guideline + Betriebshinweis**

In `CLAUDE.md` unter „Sicherheit" ergänzen: At-rest-Verschlüsselung der Blobs aktiv, wenn `STORAGE_ENCRYPTION_KEY` gesetzt (Prod-Pflicht); **DB-at-rest separat über verschlüsseltes Volume/Dateisystem (Infra) — Betriebsanweisung: Postgres-Datenverzeichnis und Storage-Mount auf verschlüsseltem Volume (LUKS bzw. verschlüsselter Hetzner-Volume) betreiben.** Key-Verlust = Datenverlust → KMS/Passwortsafe + Rotationskonzept.

- [ ] **Step 4: Commit**

```bash
git add .env.example Makefile CLAUDE.md
git commit -m "G-1: Doku — Key-Erzeugung, .env, DB-Infra-Verschluesselung"
```

---

## Self-Review

- **Spec-Abdeckung:** App-Level-Blob-Verschlüsselung (Task 3/4), Key aus Env/Envelope (Task 2/3), Bestands-Migration (Task 5), DB-Infra dokumentiert (Task 6). ✓
- **Invarianten:** `file_hash` bleibt Klartext-Hash (Verschlüsselung am Storage-Layer transparent → Worker-Reverify-Test in Task 4 beweist es); Streaming erhalten (`_IterReader`/`_FrameReader`, 64-KB-Frames). ✓
- **Offen/Folgeschritt:** Master-Key-Rotation (DEK-Re-Wrap ohne Blob-Neuverschlüsselung) ist mit diesem Envelope-Design später möglich — eigener kleiner Task, hier nicht nötig.

---

## Execution Handoff

Zwei Ausführungsoptionen:
1. **Subagent-Driven (empfohlen)** — pro Task ein frischer Subagent, Review dazwischen.
2. **Inline** — Tasks in dieser Session mit Checkpoints.
