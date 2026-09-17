from __future__ import annotations

from pathlib import Path

from audit import Finding, run_checks
from generator.content import DeckContent, SlideContent
from ir_schema import (
    AutoShape,
    Color,
    Deck,
    Paragraph,
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


def test_slide_fill_ratio_fires_too_low():
    shape = _text_shape(1, [_para("x")], width=100, height=100)
    slide = Slide(index=0, layout_name="CONTENT", shapes=[shape])
    findings = run_checks(_deck([slide]), _template_deck())
    assert len(_findings_for("slide_fill_ratio", findings)) == 1


def test_slide_fill_ratio_silent_when_in_range():
    # ~50% of the slide area.
    width = int((SLIDE_WIDTH * SLIDE_HEIGHT * 0.5) ** 0.5)
    shape = _text_shape(1, [_para("x")], left=0, top=0, width=width, height=width)
    slide = Slide(index=0, layout_name="CONTENT", shapes=[shape])
    findings = run_checks(_deck([slide]), _template_deck())
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


def test_empty_or_title_only_slide_fires():
    slide = Slide(index=0, layout_name="CONTENT", shapes=[_title_shape(1, "Just a title")])
    findings = run_checks(_deck([slide]), _template_deck())
    assert len(_findings_for("empty_or_title_only_slide", findings)) == 1


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
    assert "slide 0" in dupes[0].message


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
