"""Структурная проверка .pptx без PowerPoint: то, из-за чего он показывает «восстановить файл».

    uv run python evals/validate_pptx.py submission/*.pptx

Проверяет: все внутренние связи (rels) ведут на существующие части; у каждой части есть тип
содержимого; XML слайдов разбирается; id фигур на слайде уникальны; в presentation.xml нет
ссылок на несуществующие слайды.
"""

from __future__ import annotations

import posixpath
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

from lxml import etree

REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def validate(path: Path) -> list[str]:
    problems: list[str] = []
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        ct = etree.fromstring(z.read("[Content_Types].xml"))
        defaults = {e.get("Extension", "").lower() for e in ct.findall(f"{{{CT_NS}}}Default")}
        overrides = {e.get("PartName") for e in ct.findall(f"{{{CT_NS}}}Override")}
        for name in names:
            if name == "[Content_Types].xml" or name.endswith("/"):
                continue
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if f"/{name}" not in overrides and ext not in defaults:
                problems.append(f"нет типа содержимого: {name}")
        for name in names:
            if not name.endswith(".rels"):
                continue
            base = posixpath.dirname(posixpath.dirname(name))
            for rel in etree.fromstring(z.read(name)).findall(f"{{{REL_NS}}}Relationship"):
                if rel.get("TargetMode") == "External":
                    continue
                target = rel.get("Target", "")
                full = target.lstrip("/") if target.startswith("/") else posixpath.normpath(
                    posixpath.join(base, target)
                )
                if full not in names:
                    problems.append(f"битая связь {name} -> {target}")
        for name in sorted(n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)):
            try:
                root = etree.fromstring(z.read(name))
            except etree.XMLSyntaxError as exc:
                problems.append(f"{name}: XML не разбирается ({exc})")
                continue
            ids = [e.get("id") for e in root.iter(f"{{{P_NS}}}cNvPr")]
            dupes = [i for i, n in Counter(ids).items() if n > 1]
            if dupes:
                problems.append(f"{name}: повторяются id фигур {dupes[:5]}")
    return problems


def main(paths: list[str]) -> int:
    bad = 0
    for p in paths:
        problems = validate(Path(p))
        print(("FAIL " if problems else "ok   ") + p)
        for line in problems[:8]:
            print("     -", line)
        bad += bool(problems)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
