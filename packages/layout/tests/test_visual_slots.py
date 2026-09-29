"""A writer's chart or diagram replaces the photo frame or the text area of its slide."""

from __future__ import annotations

from generator.content import ChartSpec, DeckContent, DiagramSpec, SlideContent
from ir_schema import (
    AutoShape,
    ChartSeries,
    ChartShape,
    Deck,
    DiagramItem,
    DiagramShape,
    Paragraph,
    Picture,
    Slide,
    TextBoxShape,
    TextRun,
)
from layout import compose_deck

W, H = 12_192_000, 6_858_000


def _text(shape_id, text, *, kind, top, height, left=500_000, width=11_000_000, placeholder=None):
    return TextBoxShape(
        shape_id=shape_id,
        name=f"t{shape_id}",
        z_order=shape_id,
        left=left,
        top=top,
        width=width,
        height=height,
        is_placeholder=placeholder is not None,
        placeholder_type=placeholder,
        paragraphs=[Paragraph(runs=[TextRun(text=text, font_name="Arial", font_size_pt=18.0)])],
    )


def _photo(shape_id, left=6_500_000, top=1_600_000, width=5_000_000, height=4_500_000):
    return Picture(
        shape_id=shape_id,
        name="photo",
        z_order=shape_id,
        left=left,
        top=top,
        width=width,
        height=height,
        image_bytes_b64="AAAA",
        content_type="image/png",
    )


def _template(*shapes) -> Deck:
    title = _text(1, "Заголовок", kind="t", top=300_000, height=900_000, placeholder="TITLE (1)")
    slide = Slide(index=0, layout_name="L", shapes=[title, *shapes])
    return Deck(slide_width=W, slide_height=H, slides=[slide], theme_colors={"accent1": "0077FF"})


def _body():
    return _text(
        2,
        "Текст шаблона",
        kind="b",
        top=1_600_000,
        height=4_500_000,
        width=5_500_000,
        placeholder="BODY (2)",
    )


def _diagram(kind="process") -> DiagramSpec:
    items = [DiagramItem(label=f"Шаг {i}", detail="Пояснение", icon="drop") for i in (1, 2, 3)]
    return DiagramSpec(diagram_type=kind, items=items)


def _chart() -> ChartSpec:
    return ChartSpec(
        title="Выручка",
        unit="млн ₽",
        category_label="Год",
        categories=["2024", "2025"],
        series=[ChartSeries(name="Выручка", values=[10, 20])],
    )


def _compose(template: Deck, **fields):
    content = DeckContent(slides=[SlideContent(role="L", title="Вывод", **fields)])
    return compose_deck(content, template, "standard").slides[0]


def test_a_diagram_takes_the_photo_frame_and_keeps_the_text():
    slide = _compose(_template(_body(), _photo(3)), bullets=["Пункт"], diagram=_diagram())
    assert any(isinstance(s, DiagramShape) for s in slide.shapes)
    assert not any(isinstance(s, Picture) for s in slide.shapes)
    assert any(
        "Пункт" in "".join(r.text for p in s.paragraphs for r in p.runs)
        for s in slide.shapes
        if isinstance(s, (TextBoxShape, AutoShape))
    )
    diagram = next(s for s in slide.shapes if isinstance(s, DiagramShape))
    assert (diagram.left, diagram.top) > (6_500_000, 1_600_000)  # inside the frame's box


def test_a_diagram_without_a_photo_frame_takes_the_text_area():
    slide = _compose(_template(_body()), diagram=_diagram("timeline"))
    diagram = next(s for s in slide.shapes if isinstance(s, DiagramShape))
    assert diagram.diagram_type == "timeline"
    assert not any(s.shape_id == 2 for s in slide.shapes)  # the body placeholder is gone


def test_a_chart_is_drawn_when_the_template_has_none():
    slide = _compose(_template(_body()), chart=_chart())
    chart = next(s for s in slide.shapes if isinstance(s, ChartShape))
    assert chart.categories == ["2024", "2025"]
    assert chart.series[0].values == [10, 20]
    assert chart.unit == "млн ₽"


def test_a_drawn_visual_uses_the_templates_font_and_a_scale_size():
    slide = _compose(_template(_body()), diagram=_diagram())
    diagram = next(s for s in slide.shapes if isinstance(s, DiagramShape))
    assert diagram.font_name == "Arial"
    assert 12 <= diagram.font_size_pt <= 24


def test_a_slide_with_no_room_for_a_visual_keeps_its_points_as_bullets():
    label = _text(4, "x", kind="l", top=6_500_000, height=200_000, width=900_000)
    slide = _compose(_template(label), diagram=_diagram())
    assert not any(isinstance(s, DiagramShape) for s in slide.shapes)
    words = " ".join(
        r.text
        for s in slide.shapes
        if isinstance(s, (TextBoxShape, AutoShape))
        for p in s.paragraphs
        for r in p.runs
    )
    assert "Шаг 1" in words


def test_a_slide_without_a_visual_is_untouched():
    slide = _compose(_template(_body(), _photo(3)), bullets=["Пункт"])
    assert any(isinstance(s, Picture) for s in slide.shapes)
    assert not any(isinstance(s, (ChartShape, DiagramShape)) for s in slide.shapes)
