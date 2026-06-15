"""Textextraktion fuer txt/pdf/docx (MVP — keine Bild-Preview, kein OCR)."""

from __future__ import annotations

import io
from typing import BinaryIO

MAX_TEXT_CHARS = 1_000_000  # Datenminimierung: Volltext begrenzen

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _truncate(text: str) -> str:
    return text[:MAX_TEXT_CHARS]


def extract_text(mime: str, data: bytes) -> str | None:
    """Best-effort Textextraktion aus einem bytes-Blob.

    Komfort-Wrapper um `extract_text_from_file` fuer kleine/Test-Inhalte. Fuer
    grosse Dateien sollte der Worker `extract_text_from_file` mit einem seekbaren
    File-Objekt nutzen (kein Komplett-Blob im RAM).
    """
    return extract_text_from_file(mime, io.BytesIO(data))


def extract_text_from_file(mime: str, fileobj: BinaryIO) -> str | None:
    """Best-effort Textextraktion aus einem seekbaren File-Objekt.

    `fileobj` muss am Anfang positioniert sein (seek(0)). Gibt None zurueck,
    wenn der MIME-Typ nicht unterstuetzt wird.
    """
    if mime == "text/plain":
        return _truncate(fileobj.read().decode("utf-8", errors="replace"))
    if mime == "application/pdf":
        return _extract_pdf(fileobj)
    if mime == _DOCX_MIME:
        return _extract_docx(fileobj)
    return None


def _extract_pdf(fileobj: BinaryIO) -> str | None:
    from pypdf import PdfReader

    reader = PdfReader(fileobj)
    parts = [(page.extract_text() or "") for page in reader.pages]
    return _truncate("\n".join(parts).strip())


def _extract_docx(fileobj: BinaryIO) -> str | None:
    from docx import Document as DocxDocument

    doc = DocxDocument(fileobj)
    parts = [p.text for p in doc.paragraphs]
    return _truncate("\n".join(parts).strip())
