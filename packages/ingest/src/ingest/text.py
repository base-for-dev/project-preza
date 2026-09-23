"""Any supported document -> plain text.

Deliberately dependency-light: Markdown/text are read as-is, PDF goes through
`pypdf`, `.docx` is read straight from its OOXML (`word/document.xml`, no
python-docx needed), and `.pptx` reuses this repo's own `parser` so slide text
comes out exactly as the rest of the pipeline sees it. Anything else returns
`None` — callers skip it rather than fail the whole upload.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from ir_schema import AutoShape, Table, TextBoxShape

TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".rst", ".adoc", ".csv"}
DOC_SUFFIXES = TEXT_SUFFIXES | {".pdf", ".docx", ".pptx"}


def extract_text(path: Path) -> str | None:
    """Plain text of one file, or `None` if its format isn't supported/readable."""
    suffix = path.suffix.lower()
    try:
        if suffix in TEXT_SUFFIXES:
            return path.read_text(encoding="utf-8", errors="replace")
        if suffix == ".pdf":
            return _pdf_text(path)
        if suffix == ".docx":
            return _docx_text(path)
        if suffix == ".pptx":
            return _pptx_text(path)
    except Exception:
        # A corrupt or encrypted file is one unreadable source, not a reason
        # to fail everything else the user uploaded alongside it.
        return None
    return None


def _pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8", errors="replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)


def _pptx_text(path: Path) -> str:
    from parser.parser import parse

    deck = parse(path)
    slides: list[str] = []
    for slide in deck.slides:
        lines: list[str] = []
        for shape in slide.shapes:
            if isinstance(shape, (TextBoxShape, AutoShape)):
                for paragraph in shape.paragraphs:
                    text = "".join(run.text for run in paragraph.runs).strip()
                    if text:
                        lines.append(text)
            elif isinstance(shape, Table):
                for row in shape.rows:
                    lines.append(" | ".join(cell.text for cell in row))
        if lines:
            slides.append(f"[slide {slide.index + 1}]\n" + "\n".join(lines))
    return "\n\n".join(slides)
