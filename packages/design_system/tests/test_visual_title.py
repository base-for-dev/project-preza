"""Tests for `design_system.slots.visual_title` and char-width scaling.

uv run pytest packages/design_system
"""

from __future__ import annotations

from design_system.slots import is_title, mark_visual_titles, visual_title
from design_system.textfit import REFERENCE_CHAR_WIDTH_EM, estimate_text_height, width_scale
from ir_schema import Deck, Paragraph, Slide, TextBoxShape, TextRun


def _shape(
    shape_id: int, text: str, size: float | None, width: int = 4_000_000, **kw
) -> TextBoxShape:
    return TextBoxShape(
        shape_id=shape_id,
        name=f"s{shape_id}",
        z_order=shape_id,
        left=0,
        top=0,
        width=width,
        height=1_000_000,
        paragraphs=[Paragraph(runs=[TextRun(text=text, font_size_pt=size, **kw)])],
    )


def _slide(*shapes) -> Slide:
    return Slide(index=0, layout_name="BLANK", shapes=list(shapes))


def test_biggest_text_box_is_the_heading():
    title = _shape(1, "Goal Roadmap", 117)
    slide = _slide(title, _shape(2, "Add Company Name", 21))
    assert visual_title(slide) is title


def test_giant_number_or_glyph_neither_is_nor_outranks_the_heading():
    heading = _shape(2, "PROJECT TIMELINE", 70)
    slide = _slide(_shape(1, "02", 338), heading, _shape(3, "“", 300))
    assert visual_title(slide) is heading


def test_row_of_equal_cards_has_no_heading():
    slide = _slide(*[_shape(i, "Add a main point", 36) for i in range(3)])
    assert visual_title(slide) is None


def test_long_paragraph_is_not_a_heading():
    slide = _slide(_shape(1, "word " * 30, 40), _shape(2, "small", 12))
    assert visual_title(slide) is None


def test_real_title_placeholder_wins():
    placeholder = _shape(1, "Title", 30, is_placeholder=False)
    placeholder.placeholder_type = "TITLE (1)"
    slide = _slide(placeholder, _shape(2, "Much Bigger Words", 90))
    assert visual_title(slide) is None


def test_mark_visual_titles_makes_is_title_true():
    title = _shape(1, "Our Story", 60)
    deck = Deck(slide_width=1, slide_height=1, slides=[_slide(title, _shape(2, "body text", 18))])
    mark_visual_titles(deck)
    assert is_title(deck.slides[0].shapes[0])
    assert not is_title(deck.slides[0].shapes[1])


def test_condensed_font_fits_more_per_line_than_wide_font():
    text = "Condensed faces hold more characters on every line of a box " * 3
    narrow = _shape(1, text, 24, char_width_em=0.40)
    wide = _shape(2, text, 24, char_width_em=0.57)
    unknown = _shape(3, text, 24)
    assert width_scale(unknown.paragraphs[0].runs) == 1.0
    assert width_scale(narrow.paragraphs[0].runs) == 0.40 / REFERENCE_CHAR_WIDTH_EM
    assert estimate_text_height(narrow) < estimate_text_height(wide)
