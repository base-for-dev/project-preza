"""Structural check of an exported .pptx, without PowerPoint.

Finds what makes PowerPoint offer to "repair" a file: internal relationships
pointing at parts that do not exist, parts with no content type, slide XML that
does not parse, duplicate shape ids on a slide. The audit runs it on every
export (check `file_not_openable`); `evals/validate_pptx.py` runs it on files.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from collections import Counter
from pathlib import Path

from lxml import etree

REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def validate(path: Path) -> list[str]:
    """Problems found in the .pptx at `path`; empty when it looks openable."""
    problems: list[str] = []
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        return ["not a zip archive"]
    with archive as z:
        names = set(z.namelist())
        ct = etree.fromstring(z.read("[Content_Types].xml"))
        defaults = {e.get("Extension", "").lower() for e in ct.findall(f"{{{CT_NS}}}Default")}
        overrides = {e.get("PartName") for e in ct.findall(f"{{{CT_NS}}}Override")}
        for name in names:
            if name == "[Content_Types].xml" or name.endswith("/"):
                continue
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if f"/{name}" not in overrides and ext not in defaults:
                problems.append(f"no content type for {name}")
        for name in names:
            if not name.endswith(".rels"):
                continue
            base = posixpath.dirname(posixpath.dirname(name))
            for rel in etree.fromstring(z.read(name)).findall(f"{{{REL_NS}}}Relationship"):
                if rel.get("TargetMode") == "External":
                    continue
                target = rel.get("Target", "")
                full = (
                    target.lstrip("/")
                    if target.startswith("/")
                    else posixpath.normpath(posixpath.join(base, target))
                )
                if full not in names:
                    problems.append(f"broken relationship {name} -> {target}")
        for name in sorted(n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)):
            try:
                root = etree.fromstring(z.read(name))
            except etree.XMLSyntaxError as exc:
                problems.append(f"{name}: XML does not parse ({exc})")
                continue
            ids = [e.get("id") for e in root.iter(f"{{{P_NS}}}cNvPr")]
            dupes = [i for i, n in Counter(ids).items() if n > 1]
            if dupes:
                problems.append(f"{name}: duplicate shape ids {dupes[:5]}")
    return problems
