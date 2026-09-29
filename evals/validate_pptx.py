"""Структурная проверка .pptx без PowerPoint: то, из-за чего он показывает «восстановить файл».

    uv run python evals/validate_pptx.py submission/*.pptx

Сама проверка — `export.validate` (её же аудит запускает на каждом экспорте).
"""

from __future__ import annotations

import sys
from pathlib import Path

from export.validate import validate


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
