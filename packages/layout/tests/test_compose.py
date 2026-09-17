from __future__ import annotations

import pytest
from generator.content import DeckContent, SlideContent
from ir_schema import (
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


def _title_shape(shape_id: int, text: str = "Template title") -> TextBoxShape:
    return TextBoxShape(
        shape_id=shape_id,
        name=f"title-{shape_id}",
        z_order=0,
        left=0,
        top=0,
        width=1_000_000,
        height=200_000,
        is_placeholder=True,
        placeholder_type="TITLE (1)",
        paragraphs=[
            Paragraph(
                runs=[
                    TextRun(
                        text=text,
                        font_name="Arial",
                        font_size_pt=32.0,
                        bold=True,
                    )
                ]
            )
        ],
    )


def _body_shape(shape_id: int) -> TextBoxShape:
    return TextBoxShape(
        shape_id=shape_id,
        name=f"body-{shape_id}",
        z_order=1,
        left=0,
        top=250_000,
        width=1_000_000,
        height=800_000,
        is_placeholder=True,
        placeholder_type="BODY (2)",
        paragraphs=[
            Paragraph(runs=[TextRun(text="template body", font_name="Calibri", font_size_pt=18.0)])
        ],
    )


def _picture_shape(shape_id: int) -> Picture:
    return Picture(
        shape_id=shape_id,
        name=f"pic-{shape_id}",
        z_order=2,
        left=0,
        top=1_100_000,
        width=500_000,
        height=500_000,
        image_bytes_b64="AAAA",
        content_type="image/png",
        filename="pic.png",
    )


def _table_shape(shape_id: int) -> Table:
    return Table(
        shape_id=shape_id,
        name=f"table-{shape_id}",
        z_order=3,
        left=0,
        top=1_700_000,
        width=1_000_000,
        height=400_000,
        placeholder_type="TABLE (12)",
        rows=[
            [TableCell(paragraphs=[Paragraph(runs=[TextRun(text="a")])])],
        ],
        column_widths=[1_000_000],
        row_heights=[400_000],
    )


def _template_deck() -> Deck:
    content_slide = Slide(
        index=0,
        layout_name="CONTENT",
        shapes=[
            _title_shape(1),
            _body_shape(2),
            _picture_shape(3),
        ],
    )
    table_slide = Slide(
        index=1,
        layout_name="DATA",
        shapes=[_title_shape(10), _table_shape(11)],
    )
    return Deck(
        slide_width=9_144_000,
        slide_height=6_858_000,
        source_path="fixture.pptx",
        slides=[content_slide, table_slide],
    )


def _deck_content(bullets: list[str], body: str | None = None) -> DeckContent:
    return DeckContent(
        slides=[
            SlideContent(
                role="CONTENT",
                title="Generated Title",
                bullets=bullets,
                body=body,
            )
        ]
    )


LONG_BULLETS = [f"bullet {i}" for i in range(1, 9)]  # 8 bullets


def test_title_substituted_identically_across_variants():
    template = _template_deck()
    content = _deck_content(LONG_BULLETS, body="closing thought")

    titles = {}
    for variant in ("compact", "standard", "detailed"):
        deck = compose_deck(content, template, variant)
        slide = deck.slides[0]
        title_shape = next(
            s
            for s in slide.shapes
            if isinstance(s, TextBoxShape)
            and s.placeholder_type
            and "TITLE" in s.placeholder_type
        )
        text = "".join(run.text for p in title_shape.paragraphs for run in p.runs)
        titles[variant] = text
        # style sampled from template's existing run
        run = title_shape.paragraphs[0].runs[0]
        assert run.font_name == "Arial"
        assert run.font_size_pt == 32.0
        assert run.bold is True

    assert titles["compact"] == titles["standard"] == titles["detailed"] == "Generated Title"


def test_bullet_counts_differ_by_variant():
    template = _template_deck()
    content = _deck_content(LONG_BULLETS, body="closing thought")

    def bullet_count(variant: str) -> int:
        deck = compose_deck(content, template, variant)
        slide = deck.slides[0]
        body_shape = next(
            s
            for s in slide.shapes
            if isinstance(s, TextBoxShape)
            and s.placeholder_type
            and "BODY" in s.placeholder_type
        )
        return len(body_shape.paragraphs)

    compact = bullet_count("compact")
    standard = bullet_count("standard")
    detailed = bullet_count("detailed")

    assert compact == 3
    assert standard == 6
    # detailed = 8 bullets + 1 body paragraph appended (no dedicated body slot)
    assert detailed == 9
    assert compact < standard <= detailed


def test_body_shape_style_sampled_from_template():
    template = _template_deck()
    content = _deck_content(["only one bullet"])
    deck = compose_deck(content, template, "standard")
    slide = deck.slides[0]
    body_shape = next(
        s
        for s in slide.shapes
        if isinstance(s, TextBoxShape) and s.placeholder_type and "BODY" in s.placeholder_type
    )
    run = body_shape.paragraphs[0].runs[0]
    assert run.font_name == "Calibri"
    assert run.font_size_pt == 18.0


def test_picture_untouched_across_variants():
    template = _template_deck()
    content = _deck_content(LONG_BULLETS, body="closing thought")

    pictures = {}
    for variant in ("compact", "standard", "detailed"):
        deck = compose_deck(content, template, variant)
        slide = deck.slides[0]
        pic = next(s for s in slide.shapes if isinstance(s, Picture))
        pictures[variant] = pic

    original_pic = next(s for s in template.slides[0].shapes if isinstance(s, Picture))
    for pic in pictures.values():
        assert pic.model_dump() == original_pic.model_dump()


def test_table_content_substituted_and_clamped():
    template = _template_deck()
    big_table = [[f"r{r}c{c}" for c in range(7)] for r in range(9)]
    content = DeckContent(
        slides=[SlideContent(role="DATA", title="Data slide", table=big_table)]
    )
    deck = compose_deck(content, template, "standard")
    slide = deck.slides[0]
    table_shape = next(s for s in slide.shapes if isinstance(s, Table))
    assert len(table_shape.rows) <= 7
    assert all(len(row) <= 5 for row in table_shape.rows)
    assert table_shape.rows[0][0].text == "r0c0"


def test_table_left_untouched_when_content_has_none():
    template = _template_deck()
    content = DeckContent(slides=[SlideContent(role="DATA", title="Data slide", table=None)])
    deck = compose_deck(content, template, "standard")
    slide = deck.slides[0]
    table_shape = next(s for s in slide.shapes if isinstance(s, Table))
    original_table = next(s for s in template.slides[1].shapes if isinstance(s, Table))
    assert table_shape.model_dump() == original_table.model_dump()


def test_composed_slide_index_matches_position_not_template_slide():
    # "DATA" is template slide index 1; requesting it as the *first*
    # generated slide must not leave the composed slide carrying the
    # template's own index=1 — audit findings and export ordering key off
    # this field meaning "position in the generated deck".
    template = _template_deck()
    content = DeckContent(
        slides=[
            SlideContent(role="DATA", title="First generated slide"),
            SlideContent(role="CONTENT", title="Second generated slide"),
        ]
    )

    composed = compose_deck(content, template, "standard")

    assert [s.index for s in composed.slides] == [0, 1]


def test_unmatched_role_raises_value_error():
    template = _template_deck()
    content = DeckContent(slides=[SlideContent(role="NOT_A_REAL_ROLE", title="x")])
    with pytest.raises(ValueError, match="NOT_A_REAL_ROLE"):
        compose_deck(content, template, "standard")


def test_template_deck_not_mutated():
    template = _template_deck()
    original_title_text = "".join(
        run.text
        for shape in template.slides[0].shapes
        if isinstance(shape, TextBoxShape)
        for p in shape.paragraphs
        for run in p.runs
    )
    content = _deck_content(LONG_BULLETS)
    compose_deck(content, template, "standard")
    new_title_text = "".join(
        run.text
        for shape in template.slides[0].shapes
        if isinstance(shape, TextBoxShape)
        for p in shape.paragraphs
        for run in p.runs
    )
    assert original_title_text == new_title_text
