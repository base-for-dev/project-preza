"""Тесты на «настоящих» шаблонах не должны падать на свежем клоне.

`*.pptx` не в git (размер, лицензии), поэтому `evals/templates/` на новом клоне пуста.
Если так — до сбора тестов строим три небольших образца из кода
(`evals/generate_behance_templates.py`); тесты, которым нужен конкретный шаблон
(например, `portrait-regiona.pptx`), сами пропускаются, когда его нет.
"""

from __future__ import annotations

import runpy
from pathlib import Path

_TEMPLATES = Path(__file__).parent / "evals" / "templates"
_SCRIPT = Path(__file__).parent / "evals" / "generate_behance_templates.py"


def pytest_configure(config) -> None:
    if _TEMPLATES.is_dir() and any(_TEMPLATES.glob("*.pptx")):
        return
    if _SCRIPT.is_file():
        runpy.run_path(str(_SCRIPT), run_name="__main__")
