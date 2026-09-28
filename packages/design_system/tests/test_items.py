"""uv run pytest packages/design_system"""

from design_system import describe_slots, find_items
from ir_schema import Paragraph, Slide, TextBoxShape, TextRun

IN = 914_400


def _box(sid, left, top, w, h, text="", body=False):
    return TextBoxShape(
        shape_id=sid,
        name=f"s{sid}",
        z_order=sid,
        left=int(left * IN),
        top=int(top * IN),
        width=int(w * IN),
        height=int(h * IN),
        is_placeholder=body,
        placeholder_type="BODY (2)" if body else None,
        paragraphs=[Paragraph(runs=[TextRun(text=text)])] if text else [],
    )


def test_empty_body_placeholders_pair_into_heading_text_items_in_timeline_order():
    # Zig-zag timeline: three items on top, two below, numbered left to right.
    shapes = []
    for n, (left, top) in enumerate([(0.4, 1.6), (5.3, 1.6), (10.2, 1.6), (2.8, 5.3), (7.7, 5.3)]):
        shapes += [
            _box(10 + 2 * n, left, top, 2.8, 1.6, body=True),
            _box(11 + 2 * n, left, top + 0.4, 2.8, 1.2, body=True),
        ]
    shapes.append(_box(99, 1.3, 3.8, 1.0, 0.8, "1"))  # numbering stays out

    items = find_items(Slide(index=0, layout_name="L", shapes=shapes))

    assert items is not None and len(items) == 5
    assert all(i.heading is not None for i in items)
    assert [round(i.heading.left / IN, 1) for i in items] == [0.4, 2.8, 5.3, 7.7, 10.2]

    slots = describe_slots(Slide(index=0, layout_name="L", shapes=shapes))
    assert (slots.kind, slots.card_slots, slots.card_fields) == ("cards", 5, 2)


def test_identical_stacked_rows_are_single_items_not_pairs():
    rows = [_box(i, 0.6, 1.9 + 0.9 * i, 5.4, 0.8, body=True) for i in range(5)]

    items = find_items(Slide(index=0, layout_name="L", shapes=rows))

    assert items is not None and len(items) == 5
    assert all(i.heading is None for i in items)
    assert [i.text.shape_id for i in items] == [0, 1, 2, 3, 4]


def test_single_body_area_with_repeated_decoration_is_not_an_item_set():
    shapes = [
        _box(1, 0.6, 1.5, 8, 4, body=True),
        _box(2, 9, 1, 1, 0.3, "TOURISM"),
        _box(3, 9, 6, 1, 0.3, "TOURISM"),
    ]
    assert find_items(Slide(index=0, layout_name="L", shapes=shapes)) is None
