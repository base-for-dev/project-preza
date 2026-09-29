"""Tests for `design_system.slots` — non-content-shape detection and structure summary.

uv run pytest packages/design_system
"""

from __future__ import annotations

from design_system.slots import (
    describe_slots,
    is_data_placeholder,
    is_display_accent,
    is_functional_chrome,
    is_non_content_shape,
)
from ir_schema import Paragraph, Slide, TextBoxShape, TextRun


def _shape(shape_id: int, text: str, font_size_pt: float | None = None, **kw) -> TextBoxShape:
    return TextBoxShape(
        shape_id=shape_id,
        name=f"s{shape_id}",
        z_order=0,
        left=0,
        top=0,
        width=1_000_000,
        height=1_000_000,
        paragraphs=[Paragraph(runs=[TextRun(text=text, font_size_pt=font_size_pt)])]
        if text
        else [],
        **kw,
    )


# --- is_functional_chrome ----------------------------------------------------


def test_qr_code_label_is_chrome():
    assert is_functional_chrome(_shape(1, "QR-code"))


def test_russian_link_label_is_chrome():
    assert is_functional_chrome(_shape(1, "Ссылка"))


def test_logo_label_is_chrome():
    assert is_functional_chrome(_shape(1, "Лого"))


def test_real_sentence_mentioning_link_is_not_chrome():
    # Only a bare label counts — a real sentence that happens to use one of
    # these words must never be mistaken for chrome.
    assert not is_functional_chrome(
        _shape(1, "Перейдите по ссылке, чтобы узнать больше о продукте")
    )


def test_empty_shape_is_not_chrome():
    assert not is_functional_chrome(_shape(1, ""))


# --- is_display_accent --------------------------------------------------------


def test_large_font_short_text_is_display_accent():
    assert is_display_accent(_shape(1, "Q&A", font_size_pt=144.0))


def test_stat_placeholder_is_display_accent():
    assert is_display_accent(_shape(1, "ХХХ%данные показателя", font_size_pt=80.0))


def test_normal_body_size_is_not_display_accent():
    assert not is_display_accent(_shape(1, "Короткий заголовок", font_size_pt=24.0))


def test_large_font_but_long_text_is_not_display_accent():
    # A genuinely long sentence at a large font (an intentionally bold pull
    # quote, say) isn't the "big stat/word" pattern this targets.
    long_text = "Это довольно длинное предложение с реальным содержанием и смыслом"
    assert not is_display_accent(_shape(1, long_text, font_size_pt=48.0))


def test_is_non_content_shape_covers_both():
    assert is_non_content_shape(_shape(1, "QR-code"))
    assert is_non_content_shape(_shape(1, "Q&A", font_size_pt=144.0))
    assert not is_non_content_shape(_shape(1, "Обычный текст", font_size_pt=18.0))


# --- describe_slots: title_font_size_pt --------------------------------------


def test_describe_slots_flags_display_sized_title():
    title = _shape(1, "Q&A", font_size_pt=144.0, is_placeholder=True, placeholder_type="TITLE (1)")
    slide = Slide(index=0, layout_name="HERO", shapes=[title])
    slots = describe_slots(slide)
    assert slots.title_font_size_pt == 144.0


def test_describe_slots_leaves_normal_title_size_unset():
    title = _shape(
        1, "Обычный заголовок", font_size_pt=28.0, is_placeholder=True, placeholder_type="TITLE (1)"
    )
    slide = Slide(index=0, layout_name="NORMAL", shapes=[title])
    slots = describe_slots(slide)
    assert slots.title_font_size_pt is None


def test_describe_slots_excludes_chrome_and_accent_from_fallback():
    title = _shape(
        1, "Заголовок", font_size_pt=28.0, is_placeholder=True, placeholder_type="TITLE (1)"
    )
    qr = _shape(2, "QR-code")
    accent = _shape(3, "Q&A", font_size_pt=144.0)
    slide = Slide(index=0, layout_name="MIXED", shapes=[title, qr, accent])
    slots = describe_slots(slide)
    # Neither QR nor the display accent should register as a body/card slot.
    assert slots.body_slots == 0
    assert slots.card_slots == 0


# --- is_data_placeholder ------------------------------------------------------


def test_xx_percent_is_data_placeholder():
    assert is_data_placeholder(_shape(1, "ХХ%"))


def test_bare_xx_is_data_placeholder():
    assert is_data_placeholder(_shape(1, "XX"))


def test_xx_decimal_is_data_placeholder():
    assert is_data_placeholder(_shape(1, "X,X"))


def test_real_short_word_is_not_data_placeholder():
    assert not is_data_placeholder(_shape(1, "Итого"))


def test_is_non_content_shape_covers_data_placeholder():
    assert is_non_content_shape(_shape(1, "ХХ%"))


def test_one_line_body_strip_has_one_line_capacity():
    from design_system.slots import _text_capacity

    strip = TextBoxShape(
        shape_id=1, name="s", z_order=0, left=0, top=0, width=4_000_000, height=285_750
    )
    lines, chars = _text_capacity([strip])
    assert lines == 1
    assert chars > 8


def test_tall_body_has_multi_line_capacity():
    from design_system.slots import _text_capacity

    box = TextBoxShape(
        shape_id=1, name="b", z_order=0, left=0, top=0, width=6_000_000, height=3_000_000
    )
    lines, _ = _text_capacity([box])
    assert lines >= 8


def test_no_body_shapes_means_no_capacity():
    from design_system.slots import _text_capacity

    assert _text_capacity([]) == (None, None)


def test_classify_shapes_agrees_with_describe_slots_on_real_templates():
    from pathlib import Path

    from design_system import classify_shapes, describe_slots
    from parser import parse

    templates = sorted(Path(__file__).resolve().parents[3].glob("evals/templates/*.pptx"))
    assert templates, "no sample templates found"
    for path in templates:
        for slide in parse(path).slides:
            summary = describe_slots(slide)
            roles = list(classify_shapes(slide).values())
            assert roles.count("card") == summary.card_slots, (path.name, slide.index)
            assert roles.count("body") == summary.body_slots, (path.name, slide.index)
            assert ("title" in roles) == summary.has_title
            assert ("table" in roles) == summary.has_table
            assert ("picture" in roles) == summary.has_picture


def _slide_with_body(index: int, layout: str, extra_card: bool = False):
    from ir_schema import Slide

    shapes = [
        TextBoxShape(
            shape_id=index * 10 + 1,
            name="t",
            z_order=0,
            left=0,
            top=0,
            width=5_000_000,
            height=600_000,
            is_placeholder=True,
            placeholder_type="TITLE (1)",
            paragraphs=[Paragraph(runs=[TextRun(text="T")])],
        ),
        TextBoxShape(
            shape_id=index * 10 + 2,
            name="b",
            z_order=1,
            left=0,
            top=800_000,
            width=5_000_000,
            height=3_000_000,
            is_placeholder=True,
            placeholder_type="BODY (2)",
            paragraphs=[Paragraph(runs=[TextRun(text="B")])],
        ),
    ]
    return Slide(index=index, layout_name=layout, shapes=shapes)


def test_alternate_slides_moves_to_an_equivalent_design_of_the_same_layout():
    from design_system import alternate_slides
    from ir_schema import Deck

    deck = Deck(
        slide_width=9_144_000,
        slide_height=6_858_000,
        slides=[
            _slide_with_body(0, "1_Контент"),
            _slide_with_body(1, "5_Контент"),
            _slide_with_body(2, "7_Контент"),
            _slide_with_body(3, "Другое"),
        ],
    )
    base = [deck.slides[0]]
    assert alternate_slides(base, deck, 0)[0].index == 0
    assert alternate_slides(base, deck, 1)[0].index == 1
    assert alternate_slides(base, deck, 2)[0].index == 2
    assert alternate_slides(base, deck, 3)[0].index == 0  # cyclic


def test_alternate_slides_leaves_a_slide_with_no_equivalent_alone():
    from design_system import alternate_slides
    from ir_schema import Deck

    deck = Deck(
        slide_width=9_144_000,
        slide_height=6_858_000,
        slides=[_slide_with_body(0, "Обложка"), _slide_with_body(1, "Другое")],
    )
    assert alternate_slides([deck.slides[0]], deck, 2)[0].index == 0
