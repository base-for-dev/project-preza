"""Shrink-to-fit estimation.

uv run pytest packages/design_system
"""

from __future__ import annotations

from design_system import apply_factor, estimate_text_height, fit_factor
from ir_schema import Paragraph, TextBoxShape, TextRun


def _box(text: str, *, width=2_000_000, height=500_000, size: float | None = 18.0):
    return TextBoxShape(
        shape_id=1,
        name="b",
        z_order=0,
        left=0,
        top=0,
        width=width,
        height=height,
        paragraphs=[Paragraph(runs=[TextRun(text=text, font_size_pt=size)])],
    )


SCALE = [10.0, 12.0, 14.0, 18.0, 24.0]


def test_text_that_fits_is_untouched():
    shape = _box("Коротко", height=2_000_000)
    assert fit_factor(shape, SCALE) == 1.0


def test_overflowing_text_shrinks_onto_the_template_scale():
    shape = _box("слово " * 20, width=2_000_000, height=1_300_000)
    factor = fit_factor(shape, SCALE)
    assert factor < 1.0
    apply_factor(shape, SCALE, factor)
    size = shape.paragraphs[0].runs[0].font_size_pt
    assert size in SCALE and size < 18.0
    assert estimate_text_height(shape) <= shape.height * 1.05


def test_shrinking_stops_at_a_readable_floor():
    shape = _box("слово " * 400, height=200_000)
    apply_factor(shape, SCALE, fit_factor(shape, SCALE))
    assert shape.paragraphs[0].runs[0].font_size_pt >= 8.0


def test_inherited_size_is_made_explicit_only_when_shrinking():
    inherit = _box("слово " * 20, size=None, height=1_300_000)
    apply_factor(inherit, SCALE, fit_factor(inherit, SCALE))
    assert inherit.paragraphs[0].runs[0].font_size_pt is not None
    fine = _box("Коротко", size=None, height=2_000_000)
    apply_factor(fine, SCALE, fit_factor(fine, SCALE))
    assert fine.paragraphs[0].runs[0].font_size_pt is None


def test_empty_paragraphs_need_no_room():
    assert estimate_text_height(_box("   ", height=10)) == 0.0
