"""Repeated content items on a slide: cards, steps, stats, team members.

Real templates build a set of parallel items from several shapes each: a
step is a heading box plus a text box under it, a stat is a number plus its
caption, a team member is a name plus details. And those shapes are often
*empty* body placeholders (the sample text lives in the layout's prompt), so
"identical shapes that already carry text" (`repeated_slot_groups`) misses
them, and the whole item set collapses into one text area — all five steps
crammed into the first box, the other four showing "Образец текста".

`find_items` recovers the set: text slots are paired into (heading, text)
items by geometry — the text sits directly under a differently-sized heading
at the same left edge — then items are grouped by shape, and the biggest
group of 2+ is the slide's item set, in reading order. `describe_slots`,
`classify_shapes` and the composer all use it, so what the writer is asked
for is exactly what the composer places.
"""

from __future__ import annotations

import re

from ir_schema import AutoShape, Slide, TextBoxShape
from pydantic import BaseModel, ConfigDict

from design_system.slots import (
    TextShape,
    is_body_placeholder,
    is_data_placeholder,
    is_display_accent,
    is_functional_chrome,
    is_title,
    placeholder_kind,
    shape_has_text,
)

_EMU_PER_INCH = 914_400
_SAME_LEFT = int(0.15 * _EMU_PER_INCH)
_STACK_GAP = int(0.25 * _EMU_PER_INCH)
# Heading and text of one item differ in size; identical stacked boxes are a
# list of rows, not heading + text.
_DIFFERENT_SIZE = 0.1
# Widths of one item kind across the set may differ by rounding only.
_WIDTH_TOLERANCE = int(0.1 * _EMU_PER_INCH)
_NON_CONTENT_PLACEHOLDERS = ("PICTURE", "SLIDE_NUMBER", "DATE", "FOOTER", "HEADER")
_NUMBERING = re.compile(r"^\s*\d{1,2}[.)]?\s*$")


class Item(BaseModel):
    """One parallel item: an optional heading shape and its text shape."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    heading: TextBoxShape | AutoShape | None = None
    text: TextBoxShape | AutoShape


def _text(shape: TextShape) -> str:
    return " ".join("".join(r.text for r in p.runs) for p in shape.paragraphs).strip()


def _is_slot(shape: TextShape) -> bool:
    """A shape the composer may write item content into."""
    if is_title(shape) or is_functional_chrome(shape):
        return False
    if is_data_placeholder(shape) or is_display_accent(shape):
        return False
    kind = placeholder_kind(shape) or ""
    if any(tag in kind for tag in _NON_CONTENT_PLACEHOLDERS):
        return False
    if _NUMBERING.match(_text(shape)):
        return False  # "1", "02" — step numbering is design, kept as is
    return is_body_placeholder(shape) or shape_has_text(shape)


def _different_size(a: TextShape, b: TextShape) -> bool:
    def rel(x: int, y: int) -> float:
        return abs(x - y) / max(x, y, 1)

    return rel(a.height, b.height) > _DIFFERENT_SIZE or rel(a.width, b.width) > _DIFFERENT_SIZE


def _pairs(slots: list[TextShape]) -> list[Item]:
    """Greedy (heading, text) pairing by geometry; leftovers become single items."""
    ordered = sorted(slots, key=lambda s: (s.left, s.top))
    used: set[int] = set()
    items: list[Item] = []
    for head in ordered:
        if head.shape_id in used:
            continue
        below = [
            s
            for s in ordered
            if s.shape_id not in used
            and s.shape_id != head.shape_id
            and abs(s.left - head.left) <= _SAME_LEFT
            and head.top < s.top <= head.top + head.height + _STACK_GAP
            and _different_size(head, s)
        ]
        if below:
            text = min(below, key=lambda s: s.top)
            used.update({head.shape_id, text.shape_id})
            items.append(Item(heading=head, text=text))
    for shape in ordered:
        if shape.shape_id not in used:
            items.append(Item(text=shape))
    return items


def _signature(item: Item) -> tuple:
    if item.heading is None:
        # Singles keep the strict "identical box" rule `repeated_slot_groups`
        # always used, so plain card grids group exactly as before.
        return ("single", item.text.kind, item.text.width, item.text.height)
    return ("pair", item.heading.width // _WIDTH_TOLERANCE, item.text.width // _WIDTH_TOLERANCE)


def _reading_order(items: list[Item]) -> list[Item]:
    def anchor(item: Item) -> TextShape:
        return item.heading or item.text

    lefts = sorted(anchor(i).left for i in items)
    distinct_columns = all(b - a > _SAME_LEFT for a, b in zip(lefts, lefts[1:], strict=False))
    if distinct_columns:
        # Every item in its own column — a row or a zig-zag timeline: left to right.
        return sorted(items, key=lambda i: anchor(i).left)
    return sorted(items, key=lambda i: (anchor(i).top // _EMU_PER_INCH, anchor(i).left))


def find_items(slide: Slide) -> list[Item] | None:
    """The slide's parallel item set in reading order, or None if it has none.

    Accepted only when it accounts for the slide's structure: every body
    placeholder on the slide must belong to the set (otherwise the slide is a
    title + text-area slide with some repeated decoration, and the classic
    body logic applies).
    """
    slots = [
        s for s in slide.shapes if isinstance(s, (TextBoxShape, AutoShape)) and _is_slot(s)
    ]
    groups: dict[tuple, list[Item]] = {}
    for item in _pairs(slots):
        groups.setdefault(_signature(item), []).append(item)
    candidates = [g for g in groups.values() if len(g) >= 2]
    if not candidates:
        return None

    def weight(group: list[Item]) -> tuple[int, int]:
        area = sum(i.text.width * i.text.height for i in group)
        return (len(group), area)

    best = max(candidates, key=weight)
    members = {s.shape_id for i in best for s in (i.heading, i.text) if s is not None}
    bodies = {
        s.shape_id
        for s in slide.shapes
        if isinstance(s, (TextBoxShape, AutoShape)) and is_body_placeholder(s) and not is_title(s)
    }
    if not bodies <= members:
        return None
    return _reading_order(best)


def item_shape_ids(items: list[Item]) -> tuple[set[int], set[int]]:
    """(heading shape ids, text shape ids) of an item set."""
    headings = {i.heading.shape_id for i in items if i.heading is not None}
    return headings, {i.text.shape_id for i in items}
