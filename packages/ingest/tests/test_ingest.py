"""uv run pytest packages/ingest"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from ingest import (
    FactSheet,
    NamedText,
    RepoError,
    SourceBundle,
    digest_zip,
    extract_text,
    member_name,
)
from ingest.facts import digest_sources


def _zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)
    return buf.getvalue()


def test_digest_zip_reads_readme_docs_manifest_and_skips_deps():
    archive = _zip(
        {
            "proj-main/README.md": "# Proj\nTurns briefs into decks.",
            "proj-main/ARCHITECTURE.md": "parser -> layout",
            "proj-main/docs/usage.md": "Run it.",
            "proj-main/package.json": json.dumps(
                {"name": "proj", "description": "deck tool", "dependencies": {"next": "1"}}
            ),
            "proj-main/src/app.py": "print(1)",
            "proj-main/node_modules/x/README.md": "SHOULD NOT APPEAR",
        }
    )

    digest = digest_zip(archive, "proj")

    assert "Turns briefs into decks." in digest
    assert "parser -> layout" in digest
    assert "Run it." in digest
    assert "description: deck tool" in digest
    assert "Python 1" in digest
    assert "SHOULD NOT APPEAR" not in digest
    # GitHub's wrapping folder is stripped from paths.
    assert "proj-main/" not in digest


def test_digest_zip_rejects_non_zip():
    with pytest.raises(RepoError):
        digest_zip(b"not a zip", "x")


def test_source_text_keeps_story_first_and_respects_budget():
    bundle = SourceBundle(
        id="s",
        story="Мы начали с парсера.",
        documents=[NamedText(name="doc", text="d" * 50_000)],
        repos=[NamedText(name="repo", text="r" * 50_000)],
    )

    text = bundle.source_text(budget=10_000)

    assert text.startswith("# Team story\nМы начали с парсера.")
    assert len(text) <= 10_000 + 10
    assert "# Source: doc" in text and "# Source: repo" in text


def test_extract_text_markdown_and_unknown(tmp_path):
    md = tmp_path / "a.md"
    md.write_text("hello", encoding="utf-8")
    assert extract_text(md) == "hello"
    assert extract_text(tmp_path / "a.bin") is None


def test_extract_text_docx(tmp_path):
    path = tmp_path / "a.docx"
    path.write_bytes(
        _zip({"word/document.xml": "<w:document><w:p><w:t>Привет</w:t></w:p></w:document>"})
    )
    assert "Привет" in extract_text(path)


def test_fact_sheet_text_skips_empty_sections():
    sheet = FactSheet(project_name="Preza", problem=["Decks take days"], results=[])
    text = sheet.to_text()
    assert "Project: Preza" in text
    assert "- Decks take days" in text
    assert "Results" not in text


def test_digest_sources_sends_request_and_material():
    captured = {}

    class FakeClient:
        def complete_structured(self, **kwargs):
            captured.update(kwargs)
            return FactSheet(project_name="Preza")

    sheet = digest_sources(
        SourceBundle(id="s", story="история"), "финал хакатона, 7 минут", client=FakeClient()
    )

    assert sheet.project_name == "Preza"
    assert "финал хакатона, 7 минут" in captured["user_content"]
    assert "история" in captured["user_content"]
    assert captured["response_model"] is FactSheet


def test_member_name_recovers_non_utf8_flagged_names():
    # Simulate a macOS/Info-ZIP archive: UTF-8 bytes stored without the flag.
    info = zipfile.ZipInfo("ЛЦТ.pptx".encode().decode("cp437"))
    assert member_name(info) == "ЛЦТ.pptx"
    # Russian Windows archivers use cp866.
    info = zipfile.ZipInfo("Бренд.md".encode("cp866").decode("cp437"))
    assert member_name(info) == "Бренд.md"
    # Properly flagged names pass through untouched.
    flagged = zipfile.ZipInfo("Привет.md")
    flagged.flag_bits |= 0x800
    assert member_name(flagged) == "Привет.md"
