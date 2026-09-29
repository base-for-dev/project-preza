"""Composed slide IR -> findings.

Two entry points: `run_checks(deck, template_deck)` for the free, instant,
always-on deterministic pass (`kind="deterministic"` findings — see
checks.py and AUDIT.md/ARCHITECTURE.md), and `run_model_checks(deck, brief,
slide_images)` for the on-request, per-slide VLM pass (`kind="model"`
findings — see content_validation.py). The second needs rendered slide
images the caller supplies; this package never renders anything itself.
"""

from __future__ import annotations

from audit.catalog import CATALOG, CheckInfo
from audit.checks import run_checks
from audit.content_validation import CheckResult, SlideVerdict, judge_slide, run_model_checks
from audit.finding import Finding
from audit.fixes import FixReport, Skipped, apply_fixes, fixable

__all__ = [
    "CATALOG",
    "CheckInfo",
    "CheckResult",
    "Finding",
    "FixReport",
    "SlideVerdict",
    "Skipped",
    "apply_fixes",
    "fixable",
    "judge_slide",
    "run_checks",
    "run_model_checks",
]
