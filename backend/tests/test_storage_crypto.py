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


def test_trailing_data_after_final_frame_fails() -> None:
    enc, inner = _backend()
    enc.save("doc/v1", io.BytesIO(b"data"))
    inner.blobs["doc/v1"] += b"\x00" * 16  # angehaengte Bytes nach finalem Frame
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
    EncryptedStorageBackend(inner, keyring={1: _RING[1]}, active_key_id=1).save(
        "doc/v1", io.BytesIO(payload)
    )
    enc = EncryptedStorageBackend(inner, keyring=_RING, active_key_id=2)
    assert _read_all(enc.open_stream("doc/v1")) == payload
    assert enc.rewrap("doc/v1") is True
    assert _read_all(enc.open_stream("doc/v1")) == payload
    assert enc.rewrap("doc/v1") is False


def test_rewrap_unknown_version_fails() -> None:
    inner = _MemBackend()
    EncryptedStorageBackend(inner, keyring={1: _RING[1]}, active_key_id=1).save(
        "doc/v1", io.BytesIO(b"x")
    )
    enc = EncryptedStorageBackend(inner, keyring={2: _RING[2]}, active_key_id=2)
    with pytest.raises(StorageError, match="Key-Version"):
        enc.rewrap("doc/v1")
