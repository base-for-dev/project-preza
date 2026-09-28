"""Tests for `generator.structure.describe_structure`.

uv run pytest packages/generator
"""

from __future__ import annotations

from design_system import SlotSummary
from generator.structure import describe_structure


def test_title_only_slide_described_plainly():
    slots = SlotSummary(has_title=True)
    assert describe_structure(slots) == "a title only (no body text)"


def test_display_sized_title_gets_brevity_hint():
    # Regression: a title placeholder template-styled at 144pt (a "Q&A"-style
    # splash slide) got a full generated sentence instead of a punchy word —
    # renders fine once auto-shrunk, but defeats the layout's whole point.
    slots = SlotSummary(has_title=True, title_font_size_pt=144.0)
    described = describe_structure(slots)
    assert "144pt" in described
    assert "punchy" in described


def test_normal_title_size_has_no_hint():
    slots = SlotSummary(has_title=True, body_slots=1)
    assert "punchy" not in describe_structure(slots)


def test_display_hint_appears_alongside_body_description():
    slots = SlotSummary(has_title=True, body_slots=1, title_font_size_pt=80.0)
    described = describe_structure(slots)
    assert described.startswith("title + one text area")
    assert "80pt" in described
