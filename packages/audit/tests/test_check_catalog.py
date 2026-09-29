"""The catalog, the checks in code and AUDIT.md describe the same set."""

from __future__ import annotations

import re
from pathlib import Path

from audit import CATALOG
from audit.content_validation import _CHECKS as MODEL_CHECKS

SRC = Path(__file__).resolve().parents[1] / "src" / "audit"
REPO = Path(__file__).resolve().parents[3]
# Reported by the server, which is the only place that can export a file.
SERVER_CHECKS = {"file_not_openable"}


def _ids_in_code() -> set[str]:
    found = set(SERVER_CHECKS)
    for name in ("checks.py", "design_rules.py"):
        found |= set(re.findall(r'check="(\w+)"', (SRC / name).read_text(encoding="utf-8")))
    found |= {check_id for _, check_id, _ in MODEL_CHECKS}
    return found


def test_every_check_in_code_is_in_the_catalog_and_back():
    in_catalog = {c.id for c in CATALOG}
    assert _ids_in_code() == in_catalog


def test_catalog_ids_are_unique_and_described():
    ids = [c.id for c in CATALOG]
    assert len(ids) == len(set(ids))
    assert all(c.title and c.covers and c.group for c in CATALOG)


def test_audit_md_documents_every_check():
    text = (REPO / "AUDIT.md").read_text(encoding="utf-8")
    missing = [c.id for c in CATALOG if f"`{c.id}`" not in text]
    assert not missing, f"AUDIT.md does not mention: {missing}"


def test_only_deterministic_checks_have_automatic_fixes():
    assert not [c.id for c in CATALOG if c.kind == "model" and c.fixable]
