"""Charts and diagrams in generated content: what is allowed, kept and dropped."""

from __future__ import annotations

from design_system import SlotSummary
from generator.content import (
    ChartSpec,
    DeckContent,
    DiagramSpec,
    SlideContent,
    _build_user_prompt,
    _drop_ungrounded,
    can_hold_visual,
)
from generator.outline import Outline, SlideIntent
from ir_schema import ICON_NAMES, ChartSeries, DiagramItem


def _chart(values=(10, 20), categories=("2024", "2025"), **fields) -> ChartSpec:
    return ChartSpec(
        title="Выручка",
        unit="млн ₽",
        category_label="Год",
        categories=list(categories),
        series=[ChartSeries(name="Выручка", values=list(values))],
        **fields,
    )


def _items(n: int) -> list[DiagramItem]:
    return [DiagramItem(label=f"Шаг {i}", detail="", icon="drop") for i in range(n)]


def test_a_chart_with_a_missing_value_is_dropped():
    content = SlideContent(role="A", title="T", chart=_chart(values=(10,)))
    assert content.chart is None


def test_a_well_formed_chart_is_kept_and_becomes_a_table():
    content = SlideContent(role="A", title="T", chart=_chart())
    assert content.chart is not None
    assert content.chart.as_table() == [["Год", "Выручка"], ["2024", "10"], ["2025", "20"]]


def test_a_pie_chart_needs_exactly_one_series():
    two = ChartSpec(
        chart_type="pie",
        categories=["a", "b"],
        series=[ChartSeries(name="x", values=[1, 2]), ChartSeries(name="y", values=[3, 4])],
    )
    assert SlideContent(role="A", title="T", chart=two).chart is None


def test_a_diagram_needs_two_to_eight_items_and_trims_long_labels():
    assert SlideContent(role="A", title="T", diagram=DiagramSpec(items=_items(1))).diagram is None
    assert SlideContent(role="A", title="T", diagram=DiagramSpec(items=_items(9))).diagram is None
    long = DiagramSpec(items=[DiagramItem(label="я" * 100), DiagramItem(label="б")])
    kept = SlideContent(role="A", title="T", diagram=long).diagram
    assert kept is not None and len(kept.items[0].label) == 40


def test_an_unknown_pictogram_name_becomes_no_pictogram():
    content = SlideContent(
        role="A",
        title="T",
        diagram=DiagramSpec(items=[DiagramItem(label="a", icon="unicorn"), DiagramItem(label="b")]),
    )
    assert content.diagram.items[0].icon == ""


def test_a_slide_holds_at_most_one_visual():
    content = SlideContent(
        role="A", title="T", chart=_chart(), diagram=DiagramSpec(items=_items(3))
    )
    assert content.chart is not None and content.diagram is None


def test_only_a_photo_frame_or_a_text_area_can_hold_a_visual():
    assert can_hold_visual(SlotSummary(has_title=True, body_slots=1))
    assert can_hold_visual(SlotSummary(has_title=True, has_picture=True))
    assert not can_hold_visual(SlotSummary(has_title=True, card_slots=3))
    assert not can_hold_visual(SlotSummary(has_title=True))
    assert not can_hold_visual(None)


def _prompt(slots: SlotSummary) -> str:
    outline = Outline(slides=[SlideIntent(role="A", intent="i", summary="s")])
    return _build_user_prompt("brief", outline, [slots])


def test_the_prompt_says_where_a_visual_may_go_and_lists_the_pictograms():
    body = _prompt(SlotSummary(has_title=True, body_slots=1))
    assert '"chart" / "diagram": optional' in body
    assert "replaces the text area" in body
    assert all(name in body for name in ICON_NAMES)
    photo = _prompt(SlotSummary(has_title=True, has_picture=True))
    assert "replaces the slide's photo" in photo
    cards = _prompt(SlotSummary(has_title=True, card_slots=3))
    assert '"chart": must be null; "diagram": must be null' in cards


def test_a_chart_of_numbers_the_brief_never_gave_is_dropped():
    content = DeckContent(slides=[SlideContent(role="A", title="T", chart=_chart(values=(87, 91)))])
    _drop_ungrounded(content, "выручка растёт", [SlotSummary(body_slots=1)])
    assert content.slides[0].chart is None


def test_a_chart_of_numbers_from_the_brief_is_kept():
    brief = "выручка 10 млн в 2024 и 20 млн в 2025"
    content = DeckContent(slides=[SlideContent(role="A", title="T", chart=_chart())])
    _drop_ungrounded(content, brief, [SlotSummary(body_slots=1)])
    assert content.slides[0].chart is not None


def test_a_bare_step_number_as_a_label_gives_way_to_the_words_beside_it():
    items = [DiagramItem(label="1", detail="Пилот"), DiagramItem(label="2", detail="Запуск")]
    content = SlideContent(role="A", title="T", diagram=DiagramSpec(items=items))
    assert [i.label for i in content.diagram.items] == ["Пилот", "Запуск"]
