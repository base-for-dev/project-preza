from __future__ import annotations

from pathlib import Path

from audit import Finding, run_checks
from generator.content import DeckContent, SlideContent
from ir_schema import (
    AutoShape,
    Color,
    Deck,
    Paragraph,
    Picture,
    Slide,
    Table,
    TableCell,
    TextBoxShape,
    TextRun,
)
from layout import compose_deck
from parser import parse

SLIDE_WIDTH = 9_144_000
SLIDE_HEIGHT = 6_858_000

ALLOWED_FONT = "Arial"
ALLOWED_SIZE = 18.0
ALLOWED_COLOR = "FF0000"


def _run(text: str, font_name=ALLOWED_FONT, font_size_pt=ALLOWED_SIZE, color_rgb=ALLOWED_COLOR):
    color = Color(kind="rgb", rgb=color_rgb) if color_rgb else None
    return TextRun(text=text, font_name=font_name, font_size_pt=font_size_pt, color=color)


def _para(text: str, **kwargs) -> Paragraph:
    return Paragraph(runs=[_run(text, **kwargs)])


def _text_shape(
    shape_id: int,
    paragraphs: list[Paragraph],
    *,
    left=0,
    top=0,
    width=2_000_000,
    height=1_000_000,
    placeholder_type: str | None = None,
) -> TextBoxShape:
    return TextBoxShape(
        shape_id=shape_id,
        name=f"shape-{shape_id}",
        z_order=shape_id,
        left=left,
        top=top,
        width=width,
        height=height,
        is_placeholder=placeholder_type is not None,
        placeholder_type=placeholder_type,
        paragraphs=paragraphs,
    )


def _title_shape(shape_id: int, text: str = "Title") -> TextBoxShape:
    return _text_shape(
        shape_id,
        [_para(text)],
        top=0,
        height=500_000,
        placeholder_type="TITLE (1)",
    )


def _template_deck() -> Deck:
    """A minimal template deck whose extracted vocabulary is (Arial, 18pt, #FF0000).

    Each token appears twice so it clears `design_system.tokens.MIN_OCCURRENCES`.
    """
    slide = Slide(
        index=0,
        layout_name="CONTENT",
        shapes=[
            _title_shape(1, "Template title"),
            _text_shape(2, [_para("template body one"), _para("template body two")]),
        ],
    )
    return Deck(
        slide_width=SLIDE_WIDTH,
        slide_height=SLIDE_HEIGHT,
        source_path="template.pptx",
        slides=[slide],
    )


def _deck(slides: list[Slide]) -> Deck:
    return Deck(
        slide_width=SLIDE_WIDTH,
        slide_height=SLIDE_HEIGHT,
        source_path="generated.pptx",
        slides=slides,
    )


def _findings_for(check: str, findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.check == check]


# --- shape_out_of_bounds ---------------------------------------------------


def test_shape_out_of_bounds_fires():
    slide = Slide(
        index=0,
        layout_name="CONTENT",
        shapes=[_text_shape(1, [_para("x")], left=-100, top=0, width=2_000_000, height=500_000)],
    )
    findings = run_checks(_deck([slide]), _template_deck())
    assert len(_findings_for("shape_out_of_bounds", findings)) == 1


def test_shape_out_of_bounds_silent_on_clean_slide():
    slide = Slide(
        index=0,
        layout_name="CONTENT",
        shapes=[_text_shape(1, [_para("x")], left=0, top=0, width=2_000_000, height=500_000)],
    )
    findings = run_checks(_deck([slide]), _template_deck())
    assert _findings_for("shape_out_of_bounds", findings) == []


# --- shapes_overlap ---------------------------------------------------------


def test_shapes_overlap_fires():
    slide = Slide(
        index=0,
        layout_name="CONTENT",
        shapes=[
            _text_shape(1, [_para("a")], left=0, top=0, width=1_000_000, height=1_000_000),
            _text_shape(
                2, [_para("b")], left=100_000, top=100_000, width=1_000_000, height=1_000_000
            ),
        ],
    )
    findings = run_checks(_deck([slide]), _template_deck())
    assert len(_findings_for("shapes_overlap", findings)) == 1


def test_shapes_overlap_silent_when_shapes_have_no_text():
    # Regression: real templates layer decorative shapes on purpose (icon on
    # a badge, logo on a background bar) — those overlaps are design, not a
    # bug, and flagging them drowned the check in noise (confirmed live: 29
    # findings on a real deck, 0 of them text-on-text). Two empty shapes
    # overlapping must stay silent.
    slide = Slide(
        index=0,
        layout_name="CONTENT",
        shapes=[
            _text_shape(1, [], left=0, top=0, width=1_000_000, height=1_000_000),
            _text_shape(2, [], left=100_000, top=100_000, width=1_000_000, height=1_000_000),
        ],
    )
    findings = run_checks(_deck([slide]), _template_deck())
    assert _findings_for("shapes_overlap", findings) == []


def test_shapes_overlap_silent_when_only_one_shape_has_text():
    # Text overlapping a decorative/empty shape (a QR-code badge sitting on
    # a photo, a caption inside a colored background rect) is also typically
    # by-design layering, not a readability problem — only text-on-text is
    # flagged.
    slide = Slide(
        index=0,
        layout_name="CONTENT",
        shapes=[
            _text_shape(1, [_para("QR-code")], left=0, top=0, width=1_000_000, height=1_000_000),
            _text_shape(2, [], left=100_000, top=100_000, width=1_000_000, height=1_000_000),
        ],
    )
    findings = run_checks(_deck([slide]), _template_deck())
    assert _findings_for("shapes_overlap", findings) == []


def test_shapes_overlap_silent_when_only_the_empty_part_of_a_box_overlaps():
    # A tall title box holding one short line, and a caption under that line:
    # the boxes intersect, the words do not.
    title = _text_shape(1, [_para("Short title")], top=0, height=2_000_000, width=4_000_000)
    caption = _text_shape(2, [_para("Caption")], top=1_500_000, height=400_000, width=4_000_000)
    slide = Slide(index=0, layout_name="CONTENT", shapes=[title, caption])
    findings = run_checks(_deck([slide]), _template_deck())
    assert _findings_for("shapes_overlap", findings) == []


def test_shapes_overlap_silent_when_disjoint():
    slide = Slide(
        index=0,
        layout_name="CONTENT",
        shapes=[
            _text_shape(1, [_para("a")], left=0, top=0, width=1_000_000, height=1_000_000),
            _text_shape(
                2, [_para("b")], left=3_000_000, top=3_000_000, width=1_000_000, height=1_000_000
            ),
        ],
    )
    findings = run_checks(_deck([slide]), _template_deck())
    assert _findings_for("shapes_overlap", findings) == []


# --- text_overflow -----------------------------------------------------


def test_text_overflow_fires():
    # 10 paragraphs at 18pt in a tiny shape can't possibly fit.
    slide = Slide(
        index=0,
        layout_name="CONTENT",
        shapes=[
            _text_shape(
                1,
                [_para(f"line {i}") for i in range(10)],
                width=2_000_000,
                height=100_000,
            )
        ],
    )
    findings = run_checks(_deck([slide]), _template_deck())
    assert len(_findings_for("text_overflow", findings)) == 1


def test_text_overflow_silent_when_it_fits():
    slide = Slide(
        index=0,
        layout_name="CONTENT",
        shapes=[_text_shape(1, [_para("one line")], width=2_000_000, height=1_000_000)],
    )
    findings = run_checks(_deck([slide]), _template_deck())
    assert _findings_for("text_overflow", findings) == []


# --- font_not_in_template ---------------------------------------------------


def test_font_not_in_template_fires():
    slide = Slide(
        index=0,
        layout_name="CONTENT",
        shapes=[_text_shape(1, [_para("x", font_name="Comic Sans MS")])],
    )
    findings = run_checks(_deck([slide]), _template_deck())
    assert len(_findings_for("font_not_in_template", findings)) == 1


def test_font_not_in_template_silent_when_allowed():
    slide = Slide(index=0, layout_name="CONTENT", shapes=[_text_shape(1, [_para("x")])])
    findings = run_checks(_deck([slide]), _template_deck())
    assert _findings_for("font_not_in_template", findings) == []


# --- size_not_in_scale ------------------------------------------------------


def test_size_not_in_scale_fires():
    slide = Slide(
        index=0,
        layout_name="CONTENT",
        shapes=[_text_shape(1, [_para("x", font_size_pt=53.0)])],
    )
    findings = run_checks(_deck([slide]), _template_deck())
    assert len(_findings_for("size_not_in_scale", findings)) == 1


def test_size_not_in_scale_silent_when_allowed():
    slide = Slide(index=0, layout_name="CONTENT", shapes=[_text_shape(1, [_para("x")])])
    findings = run_checks(_deck([slide]), _template_deck())
    assert _findings_for("size_not_in_scale", findings) == []


# --- color_not_in_palette ---------------------------------------------------


def test_color_not_in_palette_fires():
    slide = Slide(
        index=0,
        layout_name="CONTENT",
        shapes=[_text_shape(1, [_para("x", color_rgb="00FF00")])],
    )
    findings = run_checks(_deck([slide]), _template_deck())
    assert len(_findings_for("color_not_in_palette", findings)) == 1


def test_color_not_in_palette_silent_when_allowed():
    slide = Slide(index=0, layout_name="CONTENT", shapes=[_text_shape(1, [_para("x")])])
    findings = run_checks(_deck([slide]), _template_deck())
    assert _findings_for("color_not_in_palette", findings) == []


def test_color_not_in_palette_theme_color_always_compliant():
    shape = _text_shape(1, [])
    shape.paragraphs = [
        Paragraph(
            runs=[
                TextRun(
                    text="x",
                    font_name=ALLOWED_FONT,
                    font_size_pt=ALLOWED_SIZE,
                    color=Color(kind="theme", theme_color="ACCENT_9"),
                )
            ]
        )
    ]
    slide = Slide(index=0, layout_name="CONTENT", shapes=[shape])
    findings = run_checks(_deck([slide]), _template_deck())
    assert _findings_for("color_not_in_palette", findings) == []


def test_autoshape_fill_color_not_in_palette_fires():
    shape = AutoShape(
        shape_id=1,
        name="rect",
        z_order=0,
        left=0,
        top=0,
        width=1_000_000,
        height=1_000_000,
        fill_color=Color(kind="rgb", rgb="123456"),
    )
    slide = Slide(index=0, layout_name="CONTENT", shapes=[shape])
    findings = run_checks(_deck([slide]), _template_deck())
    assert len(_findings_for("color_not_in_palette", findings)) == 1


# --- too_many_bullets --------------------------------------------------


def test_too_many_bullets_fires():
    shape = _text_shape(
        1,
        [_para(f"bullet {i}") for i in range(7)],
        placeholder_type="BODY (2)",
    )
    slide = Slide(index=0, layout_name="CONTENT", shapes=[shape])
    findings = run_checks(_deck([slide]), _template_deck())
    assert len(_findings_for("too_many_bullets", findings)) == 1


def test_too_many_bullets_silent_within_limit():
    shape = _text_shape(
        1,
        [_para(f"bullet {i}") for i in range(6)],
        placeholder_type="BODY (2)",
    )
    slide = Slide(index=0, layout_name="CONTENT", shapes=[shape])
    findings = run_checks(_deck([slide]), _template_deck())
    assert _findings_for("too_many_bullets", findings) == []


# --- bullet_too_long ---------------------------------------------------


def test_bullet_too_long_fires():
    long_text = " ".join(f"word{i}" for i in range(16))
    shape = _text_shape(1, [_para(long_text)])
    slide = Slide(index=0, layout_name="CONTENT", shapes=[shape])
    findings = run_checks(_deck([slide]), _template_deck())
    assert len(_findings_for("bullet_too_long", findings)) == 1


def test_bullet_too_long_silent_within_limit():
    short_text = " ".join(f"word{i}" for i in range(15))
    shape = _text_shape(1, [_para(short_text)])
    slide = Slide(index=0, layout_name="CONTENT", shapes=[shape])
    findings = run_checks(_deck([slide]), _template_deck())
    assert _findings_for("bullet_too_long", findings) == []


# --- table_too_large ---------------------------------------------------


def test_table_too_large_fires():
    table = Table(
        shape_id=1,
        name="table",
        z_order=0,
        left=0,
        top=0,
        width=1_000_000,
        height=1_000_000,
        rows=[[TableCell(paragraphs=[_para("c")]) for _ in range(6)] for _ in range(8)],
    )
    slide = Slide(index=0, layout_name="CONTENT", shapes=[table])
    findings = run_checks(_deck([slide]), _template_deck())
    assert len(_findings_for("table_too_large", findings)) == 1


def test_table_too_large_silent_within_limit():
    table = Table(
        shape_id=1,
        name="table",
        z_order=0,
        left=0,
        top=0,
        width=1_000_000,
        height=1_000_000,
        rows=[[TableCell(paragraphs=[_para("c")]) for _ in range(5)] for _ in range(7)],
    )
    slide = Slide(index=0, layout_name="CONTENT", shapes=[table])
    findings = run_checks(_deck([slide]), _template_deck())
    assert _findings_for("table_too_large", findings) == []


# --- slide_fill_ratio --------------------------------------------------


def _square(area_fraction: float) -> int:
    return int((SLIDE_WIDTH * SLIDE_HEIGHT * area_fraction) ** 0.5)


def _template_spanning_fill(low: float = 0.10, high: float = 0.60) -> Deck:
    """A template whose own slides reach `low` and `high` content coverage."""
    slides = []
    for i, fraction in enumerate((low, high)):
        side = _square(fraction)
        slides.append(
            Slide(
                index=i,
                layout_name="CONTENT",
                shapes=[_text_shape(1, [_para("t")], left=0, top=0, width=side, height=side)],
            )
        )
    return Deck(slide_width=SLIDE_WIDTH, slide_height=SLIDE_HEIGHT, slides=slides)


def test_slide_fill_ratio_fires_too_low():
    shape = _text_shape(1, [_para("x")], width=100, height=100)
    slide = Slide(index=0, layout_name="CONTENT", shapes=[shape])
    findings = run_checks(_deck([slide]), _template_spanning_fill())
    assert len(_findings_for("slide_fill_ratio", findings)) == 1


def test_slide_fill_ratio_fires_denser_than_template_ever_is():
    side = _square(0.9)
    shape = _text_shape(1, [_para("x")], left=0, top=0, width=side, height=side)
    slide = Slide(index=0, layout_name="CONTENT", shapes=[shape])
    findings = run_checks(_deck([slide]), _template_spanning_fill())
    assert len(_findings_for("slide_fill_ratio", findings)) == 1


def test_slide_fill_ratio_silent_when_within_template_range():
    side = _square(0.3)
    shape = _text_shape(1, [_para("x")], left=0, top=0, width=side, height=side)
    slide = Slide(index=0, layout_name="CONTENT", shapes=[shape])
    findings = run_checks(_deck([slide]), _template_spanning_fill())
    assert _findings_for("slide_fill_ratio", findings) == []


def test_slide_fill_ratio_does_not_double_count_stacked_shapes():
    # Two identical 40% text boxes stacked cover 40%, not 80%.
    side = _square(0.4)
    a = _text_shape(1, [_para("x")], left=0, top=0, width=side, height=side)
    b = _text_shape(2, [_para("y")], left=0, top=0, width=side, height=side)
    slide = Slide(index=0, layout_name="CONTENT", shapes=[a, b])
    findings = run_checks(_deck([slide]), _template_spanning_fill())
    assert _findings_for("slide_fill_ratio", findings) == []


def test_slide_fill_ratio_ignores_text_less_decoration():
    deco = AutoShape(
        shape_id=1, name="bg", z_order=0, left=0, top=0, width=SLIDE_WIDTH, height=SLIDE_HEIGHT
    )
    slide = Slide(index=0, layout_name="CONTENT", shapes=[deco])
    findings = run_checks(_deck([slide]), _template_spanning_fill())
    assert _findings_for("slide_fill_ratio", findings) == []


# --- placeholder_text_left --------------------------------------------------


def test_placeholder_text_left_fires():
    shape = _text_shape(1, [_para("Lorem ipsum dolor sit amet")])
    slide = Slide(index=0, layout_name="CONTENT", shapes=[shape])
    findings = run_checks(_deck([slide]), _template_deck())
    assert len(_findings_for("placeholder_text_left", findings)) == 1


def test_placeholder_text_left_silent_on_real_text():
    shape = _text_shape(1, [_para("Real slide content")])
    slide = Slide(index=0, layout_name="CONTENT", shapes=[shape])
    findings = run_checks(_deck([slide]), _template_deck())
    assert _findings_for("placeholder_text_left", findings) == []


# --- empty_or_title_only_slide ----------------------------------------------


def _body_slide(index: int) -> Slide:
    return Slide(
        index=index,
        layout_name="CONTENT",
        shapes=[_title_shape(1, f"Title {index}"), _text_shape(2, [_para(f"body {index}")])],
    )


def test_empty_or_title_only_slide_fires_in_the_middle():
    bare = Slide(index=1, layout_name="CONTENT", shapes=[_title_shape(1, "Just a title")])
    findings = run_checks(_deck([_body_slide(0), bare, _body_slide(2)]), _template_deck())
    found = _findings_for("empty_or_title_only_slide", findings)
    assert [f.slide_index for f in found] == [1]


def test_empty_or_title_only_slide_allows_a_title_only_cover_and_closing():
    bare = [
        Slide(index=i, layout_name="CONTENT", shapes=[_title_shape(1, f"Title {i}")])
        for i in (0, 2)
    ]
    findings = run_checks(_deck([bare[0], _body_slide(1), bare[1]]), _template_deck())
    assert _findings_for("empty_or_title_only_slide", findings) == []


def test_empty_or_title_only_slide_silent_with_body():
    slide = Slide(
        index=0,
        layout_name="CONTENT",
        shapes=[_title_shape(1, "Title"), _text_shape(2, [_para("some body text")])],
    )
    findings = run_checks(_deck([slide]), _template_deck())
    assert _findings_for("empty_or_title_only_slide", findings) == []


# --- duplicate_slide -----------------------------------------------------


def test_duplicate_slide_fires():
    def make_slide(index: int) -> Slide:
        return Slide(
            index=index,
            layout_name="CONTENT",
            shapes=[_title_shape(1, "Same title"), _text_shape(2, [_para("same body")])],
        )

    findings = run_checks(_deck([make_slide(0), make_slide(1)]), _template_deck())
    dupes = _findings_for("duplicate_slide", findings)
    assert len(dupes) == 1
    assert dupes[0].slide_index == 1
    assert "слайд 1" in dupes[0].message


def test_duplicate_slide_silent_when_distinct():
    slide_a = Slide(
        index=0,
        layout_name="CONTENT",
        shapes=[_title_shape(1, "Title A"), _text_shape(2, [_para("body a")])],
    )
    slide_b = Slide(
        index=1,
        layout_name="CONTENT",
        shapes=[_title_shape(1, "Title B"), _text_shape(2, [_para("body b")])],
    )
    findings = run_checks(_deck([slide_a, slide_b]), _template_deck())
    assert _findings_for("duplicate_slide", findings) == []


# --- clean composed deck against the real template --------------------------

TEMPLATE_PATH = (
    Path(__file__).parent.parent.parent.parent / "evals" / "templates" / "portrait-regiona.pptx"
)


def _real_demo_content() -> DeckContent:
    return DeckContent(
        slides=[
            SlideContent(
                role="TITLE",
                title="Engineering Offsite: Fixing Q4 Delivery Velocity",
            ),
            SlideContent(
                role="TITLE_AND_BODY",
                title="Why now",
                bullets=[
                    "Delivery velocity dropped 30% over the last two quarters.",
                    "Misalignment between teams costs more than any single project.",
                    "Technical debt is now the top blocker cited in retros.",
                ],
                body="Three focused days can reset the trajectory before Q1.",
            ),
        ]
    )


def test_real_template_composed_deck_is_near_clean():
    if not TEMPLATE_PATH.exists():
        import pytest

        pytest.skip(f"sample template not present at {TEMPLATE_PATH}")

    template_deck = parse(TEMPLATE_PATH)
    content = _real_demo_content()
    composed = compose_deck(content, template_deck, "standard")

    findings = run_checks(composed, template_deck)

    # Real, moderate, template-faithful content should not trip the
    # structural/integrity checks — the composed shapes are the template's
    # own geometry, and this content has no junk/placeholder text and no
    # duplicated slides. `font_not_in_template`/`size_not_in_scale`/
    # `color_not_in_palette` are deliberately *not* asserted zero here: a
    # real template's title slide can use a one-off style (e.g. a font only
    # the title uses) that never repeats elsewhere in the template, so
    # `extract_typography`'s own MIN_OCCURRENCES filter excludes it from the
    # "allowed" vocabulary — the composed deck reusing that exact template
    # style then legitimately doesn't match the *filtered* vocabulary. That's
    # a real (if debatable) finding, not a bug in the check.
    hard_checks = {
        "shape_out_of_bounds",
        "placeholder_text_left",
        "duplicate_slide",
    }
    hard_findings = [f for f in findings if f.check in hard_checks]
    assert hard_findings == []


# --- unsupported_figure ------------------------------------------------------


def _text_slide(texts: list[str]) -> Deck:
    shapes = [
        TextBoxShape(
            shape_id=i + 1,
            name=f"t{i}",
            z_order=i,
            left=0,
            top=i * 1_000_000,
            width=5_000_000,
            height=900_000,
            paragraphs=[Paragraph(runs=[TextRun(text=t)])],
        )
        for i, t in enumerate(texts)
    ]
    return Deck(
        slide_width=9_144_000,
        slide_height=6_858_000,
        slides=[Slide(index=0, layout_name="L", shapes=shapes)],
    )


def _blank_template_like(deck: Deck) -> Deck:
    """Same shape ids/geometry as `deck` but with empty text — a stand-in
    "template before generation" so the unsupported_figure check's
    untouched-shape skip doesn't trivially treat everything as untouched
    (which it would if the generated deck were compared against itself).
    """
    blanked_slides = []
    for slide in deck.slides:
        blanked_shapes = [s.model_copy(update={"paragraphs": []}) for s in slide.shapes]
        blanked_slides.append(slide.model_copy(update={"shapes": blanked_shapes}))
    return deck.model_copy(update={"slides": blanked_slides})


def _unsupported(deck: Deck, brief: str) -> list[Finding]:
    return [
        f
        for f in run_checks(deck, _blank_template_like(deck), source_text=brief)
        if f.check == "unsupported_figure"
    ]


def test_invented_figure_is_flagged():
    findings = _unsupported(_text_slide(["Adoption вырос на 70%"]), "Запуск 6 недель назад")
    assert len(findings) == 1
    assert "70" in findings[0].message


def test_figure_from_brief_is_not_flagged_even_with_spacing_differences():
    findings = _unsupported(_text_slide(["Охват: 40 %"]), "Охват вырос на 40% за квартал")
    assert findings == []


def test_structural_single_digits_are_ignored():
    findings = _unsupported(_text_slide(["3 опоры, шаг 2 из 4"]), "без чисел")
    assert findings == []


def test_check_skipped_without_source_text():
    deck = _text_slide(["Adoption вырос на 70%"])
    assert [f for f in run_checks(deck, deck) if f.check == "unsupported_figure"] == []


def test_untouched_template_figure_is_not_flagged():
    # Regression: a template's own step-number badges ("01", "02", ...),
    # never rewritten by composition, were flagged as model-invented figures
    # on a real generated deck. A shape whose text is unchanged from the
    # template is the template author's number, not the model's claim.
    generated = _text_slide(["01"])
    template = generated  # same shape id, same text -> "untouched"
    findings = [
        f
        for f in run_checks(generated, template, source_text="без чисел")
        if f.check == "unsupported_figure"
    ]
    assert findings == []


def test_touched_shape_figure_is_still_flagged_against_same_deck_shape():
    # Sanity check for the fixture logic above: if the shape's text DID
    # change relative to the template, the figure is still checked.
    template = _text_slide(["01"])
    generated = _text_slide(["01 — рост продаж на 99%"])
    findings = [
        f
        for f in run_checks(generated, template, source_text="без чисел")
        if f.check == "unsupported_figure"
    ]
    assert len(findings) == 1
    assert "99" in findings[0].message


def test_space_grouped_thousands_are_one_number_not_fragments():
    # Russian formatting: "12 000" is twelve thousand. It must not fragment
    # into "12" (ignored as short) + a stray "000" that flags nothing useful.
    from design_system import figures as _figures

    assert _figures("12 000 пользователей") == {"12000"}
    assert _figures("2 100 подписчиков") == {"2100"}
    assert _figures("1 000 000") == {"1000000"}


def test_picture_bleeding_off_slide_is_not_out_of_bounds():
    pic = Picture(
        shape_id=1, name="p", z_order=0, left=-100, top=0, width=SLIDE_WIDTH + 200, height=500
    )
    slide = Slide(index=0, layout_name="CONTENT", shapes=[pic])
    findings = run_checks(_deck([slide]), _template_deck())
    assert _findings_for("shape_out_of_bounds", findings) == []


def test_text_placed_off_slide_by_the_template_itself_is_not_flagged():
    shape = _text_shape(1, [_para("x")], left=-50, top=0, width=1000, height=1000)
    slide = Slide(index=0, layout_name="CONTENT", shapes=[shape])
    template = Deck(slide_width=SLIDE_WIDTH, slide_height=SLIDE_HEIGHT, slides=[slide])
    assert _findings_for("shape_out_of_bounds", run_checks(_deck([slide]), template)) == []
    assert (
        len(_findings_for("shape_out_of_bounds", run_checks(_deck([slide]), _template_deck()))) == 1
    )


def test_text_overflow_counts_wrapped_lines():
    # One short-looking paragraph, but far too long for a narrow, short box.
    shape = _text_shape(1, [_para("слово " * 60)], left=0, top=0, width=1_500_000, height=400_000)
    slide = Slide(index=0, layout_name="CONTENT", shapes=[shape])
    findings = run_checks(_deck([slide]), _template_deck())
    assert len(_findings_for("text_overflow", findings)) == 1


def test_empty_paragraphs_do_not_count_as_overflow():
    shape = _text_shape(1, [_para(""), _para(""), _para("")], width=1_000_000, height=100_000)
    slide = Slide(index=0, layout_name="CONTENT", shapes=[shape])
    findings = run_checks(_deck([slide]), _template_deck())
    assert _findings_for("text_overflow", findings) == []


def test_template_authors_own_tight_box_is_not_reported():
    box = dict(left=0, top=0, width=1_500_000, height=100_000)
    original = _text_shape(1, [_para("подпись")], **box)
    generated = _text_shape(1, [_para("надпись")], **box)
    template = Deck(
        slide_width=SLIDE_WIDTH,
        slide_height=SLIDE_HEIGHT,
        slides=[Slide(index=0, layout_name="CONTENT", shapes=[original])],
    )
    slide = Slide(index=0, layout_name="CONTENT", shapes=[generated])
    assert _findings_for("text_overflow", run_checks(_deck([slide]), template)) == []


# --- language_drift ---------------------------------------------------


def test_language_drift_fires_on_a_slide_in_the_wrong_language():
    shape = _text_shape(1, [_para("This slide is written entirely in English")])
    slide = Slide(index=0, layout_name="CONTENT", shapes=[shape])
    findings = run_checks(
        _deck([slide]), _template_deck(), source_text="Презентация о росте продаж в России"
    )
    assert len(_findings_for("language_drift", findings)) == 1


def test_language_drift_silent_when_deck_matches_the_brief():
    shape = _text_shape(1, [_para("Слайд написан по-русски, как и весь бриф")])
    slide = Slide(index=0, layout_name="CONTENT", shapes=[shape])
    findings = run_checks(
        _deck([slide]), _template_deck(), source_text="Презентация о росте продаж в России"
    )
    assert _findings_for("language_drift", findings) == []


def test_language_drift_skipped_without_a_brief():
    shape = _text_shape(1, [_para("This slide is written entirely in English")])
    slide = Slide(index=0, layout_name="CONTENT", shapes=[shape])
    findings = run_checks(_deck([slide]), _template_deck())
    assert _findings_for("language_drift", findings) == []


# --- shape's own rare style is exempt from the deck-wide vocabulary --------


def test_shape_using_its_own_rare_template_size_is_not_flagged():
    # Shape 3 is the ONLY place in the template with 53pt — below
    # tokens.MIN_OCCURRENCES, so 53pt never clears into the deck-wide scale.
    template = _deck(
        [
            _template_deck().slides[0],
            Slide(
                index=1,
                layout_name="SECTION",
                shapes=[_text_shape(3, [_para("Раздел", font_size_pt=53.0)])],
            ),
        ]
    )
    # Generation left shape 3's own size untouched (its own original value).
    generated = Slide(
        index=1,
        layout_name="SECTION",
        shapes=[_text_shape(3, [_para("Другой раздел", font_size_pt=53.0)])],
    )
    findings = run_checks(_deck([generated]), template)
    assert _findings_for("size_not_in_scale", findings) == []


def test_a_different_shape_using_that_rare_size_is_still_flagged():
    template = _deck(
        [
            _template_deck().slides[0],
            Slide(
                index=1,
                layout_name="SECTION",
                shapes=[_text_shape(3, [_para("Раздел", font_size_pt=53.0)])],
            ),
        ]
    )
    # Shape 99 never had 53pt in the template — borrowing shape 3's rare size
    # doesn't make it allowed anywhere.
    generated = Slide(
        index=1,
        layout_name="SECTION",
        shapes=[_text_shape(99, [_para("Другой текст", font_size_pt=53.0)])],
    )
    findings = run_checks(_deck([generated]), template)
    assert len(_findings_for("size_not_in_scale", findings)) == 1


def test_shape_using_its_own_rare_template_font_and_color_is_not_flagged():
    template = _deck(
        [
            _template_deck().slides[0],
            Slide(
                index=1,
                layout_name="SECTION",
                shapes=[_text_shape(3, [_para("Раздел", font_name="Impact", color_rgb="112233")])],
            ),
        ]
    )
    generated = Slide(
        index=1,
        layout_name="SECTION",
        shapes=[_text_shape(3, [_para("Другой", font_name="Impact", color_rgb="112233")])],
    )
    findings = run_checks(_deck([generated]), template)
    assert _findings_for("font_not_in_template", findings) == []
    assert _findings_for("color_not_in_palette", findings) == []


def test_shapes_overlap_tolerates_what_the_template_itself_overlaps():
    def pair(long_text: str) -> list[Slide]:
        back = _text_shape(1, [_para(long_text)], top=0, height=2_000_000)
        front = _text_shape(2, [_para(long_text)], top=500_000, height=800_000)
        return [Slide(index=0, layout_name="CONTENT", shapes=[back, front], source_index=0)]

    template = _deck(pair("слово " * 80))
    composed = _deck(pair("слово " * 80))
    assert _findings_for("shapes_overlap", run_checks(composed, template)) == []
    # The same pair with no such precedent in the template is a defect.
    bare = _deck([Slide(index=0, layout_name="CONTENT", shapes=[])])
    assert len(_findings_for("shapes_overlap", run_checks(composed, bare))) == 1
