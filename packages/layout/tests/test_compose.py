from __future__ import annotations

import pytest
from generator.content import DeckContent, SlideContent
from ir_schema import (
    AutoShape,
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
        width=6_000_000,
        height=800_000,
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
        theme_colors={"dk1": "000000", "lt1": "FFFFFF"},
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
            if isinstance(s, TextBoxShape) and s.placeholder_type and "TITLE" in s.placeholder_type
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
            if isinstance(s, TextBoxShape) and s.placeholder_type and "BODY" in s.placeholder_type
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
    content = DeckContent(slides=[SlideContent(role="DATA", title="Data slide", table=big_table)])
    deck = compose_deck(content, template, "standard")
    slide = deck.slides[0]
    table_shape = next(s for s in slide.shapes if isinstance(s, Table))
    assert len(table_shape.rows) <= 7
    assert all(len(row) <= 5 for row in table_shape.rows)
    assert table_shape.rows[0][0].text == "r0c0"


def test_table_without_content_keeps_its_grid_but_not_the_template_text():
    template = _template_deck()
    content = DeckContent(slides=[SlideContent(role="DATA", title="Data slide", table=None)])
    deck = compose_deck(content, template, "standard")
    slide = deck.slides[0]
    table_shape = next(s for s in slide.shapes if isinstance(s, Table))
    original_table = next(s for s in template.slides[1].shapes if isinstance(s, Table))
    assert len(table_shape.rows) == len(original_table.rows)
    assert all(not cell.text for row in table_shape.rows for cell in row)


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


def test_composed_deck_carries_theme_colors_from_template():
    # compose_deck rebuilds the Deck wrapper around composed_slides — a
    # regression let this drop deck-level fields that aren't `slides` itself
    # (theme_colors is resolved once per deck by the parser, not per slide,
    # so it isn't recovered by copying individual slides).
    template = _template_deck()
    content = _deck_content(["one"])

    composed = compose_deck(content, template, "standard")

    assert composed.theme_colors == template.theme_colors


def _card(shape_id: int, left: int, text: str) -> AutoShape:
    return AutoShape(
        shape_id=shape_id,
        name=f"card-{shape_id}",
        z_order=shape_id,
        left=left,
        top=1_000_000,
        width=2_000_000,
        height=2_000_000,
        placeholder_type=None,
        paragraphs=[Paragraph(runs=[TextRun(text=text, font_name="Arial", font_size_pt=18.0)])],
    )


def _caption(shape_id: int, left: int) -> TextBoxShape:
    return TextBoxShape(
        shape_id=shape_id,
        name=f"cap-{shape_id}",
        z_order=shape_id,
        left=left,
        top=3_200_000,
        width=500_000,
        height=200_000,
        placeholder_type=None,
        paragraphs=[Paragraph(runs=[TextRun(text="Текст")])],
    )


def _card_grid_deck() -> Deck:
    # A designed 3-card layout: one TITLE + three identically-sized card
    # autoshapes (each with prompt text) + three identically-sized caption
    # boxes. No BODY placeholder anywhere.
    slide = Slide(
        index=0,
        layout_name="CARDS",
        shapes=[
            _title_shape(1, "Заголовок"),
            _card(2, 0, "Заголовок"),
            _card(3, 2_500_000, "Заголовок"),
            _card(4, 5_000_000, "Заголовок"),
            _caption(5, 0),
            _caption(6, 2_500_000),
            _caption(7, 5_000_000),
        ],
    )
    return Deck(
        slide_width=9_144_000,
        slide_height=6_858_000,
        theme_colors={},
        slides=[slide],
    )


def test_repeated_cards_each_get_a_distinct_bullet():
    deck = _card_grid_deck()
    content = DeckContent(
        slides=[SlideContent(role="CARDS", title="T", bullets=["one", "two", "three"])]
    )

    composed = compose_deck(content, deck, "standard")
    cards = [s for s in composed.slides[0].shapes if s.name.startswith("card-")]
    texts = ["".join(r.text for p in c.paragraphs for r in p.runs) for c in cards]

    # One distinct bullet per card, in left-to-right reading order — not all
    # dumped into one card, not leaking the "Заголовок" prompt.
    assert sorted(texts) == ["one", "three", "two"]
    assert "Заголовок" not in texts


def test_repeated_caption_scaffolding_is_blanked_not_leaked():
    deck = _card_grid_deck()
    content = DeckContent(slides=[SlideContent(role="CARDS", title="T", bullets=["a", "b", "c"])])

    composed = compose_deck(content, deck, "standard")
    caps = [s for s in composed.slides[0].shapes if s.name.startswith("cap-")]
    cap_texts = ["".join(r.text for p in c.paragraphs for r in p.runs) for c in caps]

    # Unfilled repeated scaffolding is emptied, never left showing "Текст".
    assert cap_texts == ["", "", ""]


def test_fewer_bullets_than_cards_clears_leftover_cards():
    deck = _card_grid_deck()
    content = DeckContent(slides=[SlideContent(role="CARDS", title="T", bullets=["only one"])])

    composed = compose_deck(content, deck, "standard")
    cards = [s for s in composed.slides[0].shapes if s.name.startswith("card-")]
    texts = ["".join(r.text for p in c.paragraphs for r in p.runs) for c in cards]

    assert sorted(texts) == ["", "", "only one"]  # no leftover "Заголовок"


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


def test_unique_unfilled_leftover_shapes_are_cleared_not_just_repeated_groups():
    # Regression: a real template instance had 2 same-size cards (filled
    # correctly) plus two ONE-OFF differently-sized leftover labels with no
    # size-twin on that slide ("Заметка", "Кейс") — a repeated-group-only
    # clear left them leaking real template sample text into generated decks.
    slide = Slide(
        index=0,
        layout_name="MIXED",
        shapes=[
            _title_shape(1, "Заголовок"),
            _card(2, 0, "Заголовок"),
            _card(3, 2_500_000, "Заголовок"),
            AutoShape(
                shape_id=8,
                name="note",
                z_order=8,
                left=5_000_000,
                top=1_000_000,
                width=1_234_567,  # unique size: no size-twin on this slide
                height=654_321,
                placeholder_type=None,
                paragraphs=[Paragraph(runs=[TextRun(text="Заметка")])],
            ),
            AutoShape(
                shape_id=9,
                name="case-tag",
                z_order=9,
                left=6_500_000,
                top=1_000_000,
                width=987_654,  # a different unique size
                height=321_098,
                placeholder_type=None,
                paragraphs=[Paragraph(runs=[TextRun(text="Кейс")])],
            ),
        ],
    )
    deck = Deck(slide_width=9_144_000, slide_height=6_858_000, theme_colors={}, slides=[slide])
    content = DeckContent(slides=[SlideContent(role="MIXED", title="T", bullets=["a", "b"])])

    composed = compose_deck(content, deck, "standard")
    texts = {
        s.name: "".join(r.text for p in s.paragraphs for r in p.runs)
        for s in composed.slides[0].shapes
        if s.name in ("note", "case-tag")
    }
    assert texts == {"note": "", "case-tag": ""}


def test_speaker_notes_carried_onto_composed_slide():
    content = _deck_content(["a"])
    content.slides[0].speaker_notes = "Говорим о главном."

    deck = compose_deck(content, _template_deck(), "standard")

    assert deck.slides[0].notes == "Говорим о главном."


def test_repeated_cards_shrink_together_to_the_same_size():
    from design_system import extract_typography  # noqa: F401
    from generator.content import DeckContent, SlideContent
    from ir_schema import AutoShape, Deck, Paragraph, Slide, TextRun
    from layout import compose_deck

    def card(i: int, text: str) -> AutoShape:
        return AutoShape(
            shape_id=i,
            name=f"c{i}",
            z_order=i,
            left=i * 1_000_000,
            top=0,
            width=900_000,
            height=400_000,
            paragraphs=[Paragraph(runs=[TextRun(text=text, font_size_pt=18.0)])],
        )

    template = Deck(
        slide_width=9_144_000,
        slide_height=6_858_000,
        slides=[
            Slide(
                index=0,
                layout_name="Cards",
                shapes=[card(1, "Карточка один"), card(2, "Карточка два")],
            )
        ],
    )
    content = DeckContent(
        slides=[
            SlideContent(
                role="Cards",
                title="T",
                bullets=["Ок", "Очень длинная подпись которая не влезает в маленькую карточку"],
            )
        ]
    )
    deck = compose_deck(content, template, "standard")
    sizes = {
        s.paragraphs[0].runs[0].font_size_pt
        for s in deck.slides[0].shapes
        if isinstance(s, AutoShape) and s.paragraphs[0].runs
    }
    assert len(sizes) == 1
    assert next(iter(sizes)) < 18.0


def _prune_fixture(*, keep_text_in_plate: bool):
    from generator.content import DeckContent, SlideContent
    from ir_schema import AutoShape, Deck, Paragraph, Slide, TextBoxShape, TextRun
    from layout import compose_deck

    def para(text: str) -> list[Paragraph]:
        return [Paragraph(runs=[TextRun(text=text, font_size_pt=14.0)])] if text else []

    title = TextBoxShape(
        shape_id=1,
        name="t",
        z_order=0,
        left=0,
        top=0,
        width=6_000_000,
        height=800_000,
        is_placeholder=True,
        placeholder_type="TITLE (1)",
        paragraphs=para("Заголовок"),
    )
    background = AutoShape(
        shape_id=2, name="bg", z_order=0, left=0, top=0, width=9_144_000, height=6_858_000
    )
    plate = AutoShape(
        shape_id=3,
        name="plate",
        z_order=1,
        left=500_000,
        top=3_000_000,
        width=3_000_000,
        height=1_500_000,
    )
    label = TextBoxShape(
        shape_id=4,
        name="note",
        z_order=2,
        left=600_000,
        top=3_100_000,
        width=2_000_000,
        height=400_000,
        paragraphs=para("Lorem ipsum"),
    )
    main_body = TextBoxShape(
        shape_id=6,
        name="main",
        z_order=3,
        left=500_000,
        top=1_000_000,
        width=6_000_000,
        height=1_500_000,
        is_placeholder=True,
        placeholder_type="BODY (2)",
        paragraphs=para("Текст"),
    )
    shapes = [title, background, plate, label]
    if keep_text_in_plate:
        shapes.append(
            TextBoxShape(
                shape_id=5,
                name="body",
                z_order=3,
                left=600_000,
                top=3_600_000,
                width=2_000_000,
                height=600_000,
                is_placeholder=True,
                placeholder_type="BODY (2)",
                paragraphs=para("Текст"),
            )
        )
    shapes.append(main_body)
    template = Deck(
        slide_width=9_144_000,
        slide_height=6_858_000,
        slides=[Slide(index=0, layout_name="L", shapes=shapes)],
    )
    content = DeckContent(slides=[SlideContent(role="L", title="T", bullets=["Пункт"])])
    return compose_deck(content, template, "standard").slides[0]


def test_emptied_callout_loses_its_orphaned_plate_but_not_the_background():
    ids = {s.shape_id for s in _prune_fixture(keep_text_in_plate=False).shapes}
    assert 3 not in ids and 4 not in ids  # plate + blanked caption gone
    assert 2 in ids and 1 in ids  # full-slide background and title stay


def test_plate_holding_filled_text_is_kept():
    ids = {s.shape_id for s in _prune_fixture(keep_text_in_plate=True).shapes}
    assert 3 in ids


def _ph(sid, left, top, w, h, text=""):
    IN = 914_400
    return TextBoxShape(
        shape_id=sid,
        name=f"b{sid}",
        z_order=sid,
        left=int(left * IN),
        top=int(top * IN),
        width=int(w * IN),
        height=int(h * IN),
        is_placeholder=True,
        placeholder_type="BODY (2)",
        paragraphs=[Paragraph(runs=[TextRun(text=text)])] if text else [],
    )


def _item_template() -> Deck:
    shapes = [_title_shape(1)]
    for n, left in enumerate([0.5, 4.5, 8.5]):
        shapes += [_ph(10 + 2 * n, left, 1.5, 3.0, 0.7), _ph(11 + 2 * n, left, 2.3, 3.0, 1.5)]
    shapes.append(
        TextBoxShape(
            shape_id=50,
            name="sample",
            z_order=50,
            left=0,
            top=6_000_000,
            width=2_000_000,
            height=300_000,
            paragraphs=[Paragraph(runs=[TextRun(text="Имя Фамилия")])],
        )
    )
    return Deck(
        slide_width=12_192_000,
        slide_height=6_858_000,
        slides=[Slide(index=4, layout_name="STATS", shapes=shapes)],
    )


def _texts(slide) -> dict[int, str]:
    return {
        s.shape_id: "".join(r.text for p in s.paragraphs for r in p.runs)
        for s in slide.shapes
        if isinstance(s, TextBoxShape)
    }


def test_two_field_items_get_heading_and_text_and_leftovers_are_cleared():
    content = DeckContent(
        slides=[
            SlideContent(
                role="STATS",
                title="Итоги",
                bullets=["25 секунд — генерация колоды", "5 шаблонов — проверено"],
            )
        ]
    )

    deck = compose_deck(content, _item_template(), "standard")
    texts = _texts(deck.slides[0])

    assert texts[10] == "25 секунд" and texts[11] == "генерация колоды"
    assert texts[12] == "5 шаблонов" and texts[13] == "проверено"
    # Third item had no content: its empty placeholders are dropped entirely.
    assert 14 not in texts and 15 not in texts
    # Template sample text nobody wrote over is blanked.
    assert texts[50] == ""
    # Export clones this exact template slide.
    assert deck.slides[0].source_index == 4


def test_plate_grows_to_fit_a_long_title():
    from ir_schema import AutoShape

    IN = 914_400
    title = _title_shape(1, "x")
    title.left, title.top, title.width, title.height = (
        int(0.6 * IN),
        int(0.5 * IN),
        10 * IN,
        int(0.4 * IN),
    )
    plate = AutoShape(
        shape_id=2,
        name="plate",
        z_order=0,
        left=int(0.4 * IN),
        top=int(0.4 * IN),
        width=int(3.0 * IN),
        height=int(0.7 * IN),
    )
    deck = Deck(
        slide_width=12 * IN,
        slide_height=7 * IN,
        slides=[Slide(index=0, layout_name="T", shapes=[plate, title])],
    )
    content = DeckContent(
        slides=[
            SlideContent(role="T", title="Очень длинный заголовок, который не влезает в плашку")
        ]
    )

    composed = compose_deck(content, deck, "standard")

    grown = next(s for s in composed.slides[0].shapes if s.shape_id == 2)
    assert grown.width > 3 * IN
    assert grown.left + grown.width <= title.left + title.width


def _chart_deck() -> Deck:
    from ir_schema import PassthroughShape

    chart = PassthroughShape(
        shape_id=9,
        name="chart",
        z_order=2,
        left=0,
        top=0,
        width=100,
        height=100,
        original_shape_type="CHART (3)",
        raw_xml="<p:graphicFrame/>",
    )
    return Deck(
        slide_width=9_144_000,
        slide_height=6_858_000,
        slides=[Slide(index=0, layout_name="S", shapes=[_title_shape(1), chart])],
    )


def test_chart_without_numbers_is_removed_not_shown_with_sample_data():
    content = DeckContent(slides=[SlideContent(role="S", title="Итоги")])
    deck = compose_deck(content, _chart_deck(), "standard")
    assert all(s.shape_id != 9 for s in deck.slides[0].shapes)


def test_chart_with_numeric_table_keeps_the_data():
    table = [["Метрика", "Секунды"], ["Генерация", "25"]]
    content = DeckContent(slides=[SlideContent(role="S", title="Итоги", table=table)])
    deck = compose_deck(content, _chart_deck(), "standard")
    chart = next(s for s in deck.slides[0].shapes if s.shape_id == 9)
    assert chart.chart_data == table
