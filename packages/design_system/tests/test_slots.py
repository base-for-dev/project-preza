"""Tests for `design_system.slots` — non-content-shape detection and structure summary.

    uv run pytest packages/design_system
"""

from __future__ import annotations

from design_system.slots import (
    describe_slots,
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
