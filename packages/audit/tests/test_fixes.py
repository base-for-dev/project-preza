"""Each repair in audit.fixes, and that fixing never mutates the caller's deck."""

from __future__ import annotations

from audit import Finding, apply_fixes, fixable, run_checks
from ir_schema import (
    Color,
    Deck,
    Paragraph,
    Slide,
    Table,
    TableCell,
    TextBoxShape,
    TextRun,
)

W, H = 9_144_000, 6_858_000


def _run(text, size=18.0, color="000000", font="Arial"):
    return TextRun(text=text, font_name=font, font_size_pt=size, color=Color(kind="rgb", rgb=color))


def _box(
    shape_id,
    text,
    *,
    left=914_400,
    top=914_400,
    width=3_000_000,
    height=600_000,
    size=18.0,
    color="000000",
    font="Arial",
    placeholder=None,
):
    return TextBoxShape(
        shape_id=shape_id,
        name=f"t{shape_id}",
        z_order=shape_id,
        left=left,
        top=top,
        width=width,
        height=height,
        paragraphs=[Paragraph(runs=[_run(text, size, color, font)])],
        placeholder_type=placeholder,
    )


def _template():
    body = [
        _box(1, "a", size=18.0, color="000000"),
        _box(2, "b", size=18.0, color="000000", top=2_000_000),
        _box(3, "c", size=24.0, color="FF0000", top=3_000_000),
        _box(4, "d", size=24.0, color="FF0000", top=4_000_000),
    ]
    return Deck(
        slide_width=W,
        slide_height=H,
        slides=[
            Slide(index=0, layout_name="L", shapes=body, background=Color(kind="rgb", rgb="FFFFFF"))
        ],
    )


def _deck(*shapes, slides=1):
    made = [
        Slide(
            index=i,
            layout_name="L",
            shapes=[s.model_copy(deep=True) for s in shapes],
            background=Color(kind="rgb", rgb="FFFFFF"),
        )
        for i in range(slides)
    ]
    return Deck(slide_width=W, slide_height=H, slides=made)


def _fix(deck, check, brief=""):
    template = _template()
    findings = [
        f for f in run_checks(deck, template, source_text=brief or None) if f.check == check
    ]
    assert findings, f"the deck should trigger {check}"
    return findings, apply_fixes(deck, template, findings, brief)


def test_overflowing_text_is_shrunk_to_a_size_from_the_template():
    long_text = "слово " * 60
    deck = _deck(_box(9, long_text, height=500_000, width=3_000_000, size=24.0))
    findings, report = _fix(deck, "text_overflow")
    assert report.applied == findings
    assert report.deck.slides[0].shapes[0].paragraphs[0].runs[0].font_size_pt < 24.0


def test_off_scale_size_snaps_to_the_nearest_template_size():
    deck = _deck(_box(9, "hello", size=20.0, left=914_400, top=1_400_000))
    _, report = _fix(deck, "size_not_in_scale")
    assert report.deck.slides[0].shapes[0].paragraphs[0].runs[0].font_size_pt in (18.0, 24.0)


def test_foreign_font_becomes_the_template_font():
    deck = _deck(_box(9, "hello", font="Comic Sans MS"))
    _, report = _fix(deck, "font_not_in_template")
    assert report.deck.slides[0].shapes[0].paragraphs[0].runs[0].font_name == "Arial"


def test_foreign_colour_becomes_the_nearest_palette_colour():
    deck = _deck(_box(9, "hello", color="FE1010"))
    _, report = _fix(deck, "color_not_in_palette")
    assert report.deck.slides[0].shapes[0].paragraphs[0].runs[0].color.rgb == "FF0000"


def test_shape_off_the_slide_is_moved_back_in():
    deck = _deck(_box(9, "hello", left=W - 500_000))
    _, report = _fix(deck, "shape_out_of_bounds")
    shape = report.deck.slides[0].shapes[0]
    assert shape.left + shape.width <= W


def test_overlapping_text_blocks_are_pulled_apart():
    a = _box(8, "заголовок " * 8, top=914_400, width=3_000_000, height=900_000)
    b = _box(9, "подпись " * 8, top=1_000_000, width=3_000_000, height=900_000)
    findings, report = _fix(_deck(a, b), "shapes_overlap")
    assert report.applied
    again = [f for f in run_checks(report.deck, _template()) if f.check == "shapes_overlap"]
    assert not again


def test_pale_text_is_recoloured_for_contrast():
    deck = _deck(_box(9, "pale", color="DDDDDD", left=1_500_000, top=1_400_000))
    _, report = _fix(deck, "low_contrast")
    assert report.deck.slides[0].shapes[0].paragraphs[0].runs[0].color.rgb in ("000000", "FF0000")


def test_extra_bullets_are_cut_to_the_limit():
    many = TextBoxShape(
        shape_id=9,
        name="body",
        z_order=1,
        left=914_400,
        top=914_400,
        width=4_000_000,
        height=4_000_000,
        placeholder_type="BODY (2)",
        paragraphs=[Paragraph(runs=[_run(f"пункт {i}")]) for i in range(9)],
    )
    _, report = _fix(_deck(many), "too_many_bullets")
    assert len(report.deck.slides[0].shapes[0].paragraphs) == 6


def test_a_long_bullet_is_shortened_without_a_model():
    text = " ".join(f"слово{i}" for i in range(25))
    body = TextBoxShape(
        shape_id=9,
        name="body",
        z_order=1,
        left=914_400,
        top=914_400,
        width=6_000_000,
        height=3_000_000,
        placeholder_type="BODY (2)",
        paragraphs=[Paragraph(runs=[_run(text)])],
    )
    _, report = _fix(_deck(body), "bullet_too_long")
    fixed = report.deck.slides[0].shapes[0].paragraphs[0].runs[0].text
    assert len(fixed.split()) <= 15


def test_an_oversized_table_is_trimmed():
    cell = TableCell(paragraphs=[Paragraph(runs=[_run("x")])])
    table = Table(
        shape_id=9,
        name="tbl",
        z_order=1,
        left=100_000,
        top=100_000,
        width=5_000_000,
        height=4_000_000,
        rows=[[cell] * 7 for _ in range(10)],
        column_widths=[700_000] * 7,
        row_heights=[400_000] * 10,
    )
    _, report = _fix(_deck(table), "table_too_large")
    fixed = report.deck.slides[0].shapes[0]
    assert len(fixed.rows) == 7 and len(fixed.rows[0]) == 5


def test_placeholder_text_is_removed():
    deck = _deck(_box(9, "Lorem ipsum dolor"))
    _, report = _fix(deck, "placeholder_text_left")
    assert report.deck.slides[0].shapes[0].paragraphs[0].runs[0].text == ""


def test_an_invented_figure_is_cut_from_the_text():
    deck = _deck(_box(9, "Рост на 87% за год"))
    _, report = _fix(deck, "unsupported_figure", brief="Рост за год")
    assert "87" not in report.deck.slides[0].shapes[0].paragraphs[0].runs[0].text


def test_an_empty_middle_slide_is_deleted_and_slides_renumbered():
    title = _box(9, "Только заголовок", placeholder="TITLE (1)")
    body = _box(9, "и содержание", placeholder="TITLE (1)")
    extra = _box(10, "текст", top=2_000_000)
    deck = Deck(
        slide_width=W,
        slide_height=H,
        slides=[
            Slide(index=0, layout_name="L", shapes=[body, extra]),
            Slide(index=1, layout_name="L", shapes=[title]),
            Slide(index=2, layout_name="L", shapes=[body, extra]),
        ],
    )
    _, report = _fix(deck, "empty_or_title_only_slide")
    assert [s.index for s in report.deck.slides] == [0, 1]


def test_findings_that_need_a_person_are_skipped_with_a_reason():
    finding = Finding(check="slide_fill_ratio", slide_index=0, message="sparse")
    model = Finding(check="title_states_conclusion", kind="model", slide_index=0, message="topic")
    report = apply_fixes(_deck(_box(9, "x")), _template(), [finding, model])
    assert not report.applied
    assert [s.finding.check for s in report.skipped] == [
        "slide_fill_ratio",
        "title_states_conclusion",
    ]
    assert all(s.reason for s in report.skipped)


def test_the_callers_deck_is_never_modified():
    deck = _deck(_box(9, "hello", font="Comic Sans MS"))
    before = deck.model_dump_json()
    _fix(deck, "font_not_in_template")
    assert deck.model_dump_json() == before


def test_fixable_tells_the_ui_which_findings_have_a_repair():
    assert fixable("text_overflow")
    assert not fixable("slide_fill_ratio")
    assert not fixable("title_states_conclusion")
