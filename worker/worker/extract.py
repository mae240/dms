"""Textextraktion fuer txt/pdf/docx (MVP — keine Bild-Preview, kein OCR)."""

from __future__ import annotations

import io

MAX_TEXT_CHARS = 1_000_000  # Datenminimierung: Volltext begrenzen

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _truncate(text: str) -> str:
    return text[:MAX_TEXT_CHARS]


def extract_text(mime: str, data: bytes) -> str | None:
    """Best-effort Textextraktion. Gibt None zurueck, wenn nicht unterstuetzt."""
    if mime == "text/plain":
        return _truncate(data.decode("utf-8", errors="replace"))
    if mime == "application/pdf":
        return _extract_pdf(data)
    if mime == _DOCX_MIME:
        return _extract_docx(data)
    return None


def _extract_pdf(data: bytes) -> str | None:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts = [(page.extract_text() or "") for page in reader.pages]
    return _truncate("\n".join(parts).strip())


def _extract_docx(data: bytes) -> str | None:
    from docx import Document as DocxDocument

    doc = DocxDocument(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    return _truncate("\n".join(parts).strip())
