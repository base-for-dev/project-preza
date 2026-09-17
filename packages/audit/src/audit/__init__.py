"""Composed slide IR -> findings.

Single entry point: `run_checks(deck, template_deck)`. See `checks.py` for
each individual deterministic check and AUDIT.md/ARCHITECTURE.md for how
this fits the pipeline. Model-graded (`kind="model"`) findings aren't
implemented yet — `Finding.kind` is `Literal["deterministic"]` for now, kept
as a field so the eventual model-graded findings share the same shape.
"""

from __future__ import annotations

from audit.checks import Finding, run_checks

__all__ = ["Finding", "run_checks"]
