"""Template slide structure: what content slots does a slide actually offer?

A layout name ("MAIN_POINT", "15_Титульный слайд") says nothing on its own
about how a slide is built — one text block? three cards? a table? Both the
LLM stages (`generator`: which layout to pick, how much to write) and the
composer (`layout`: where to put it) need the same answer, so the analysis
lives here, below both, and is purely structural over the IR — no names,
positions-as-labels, or locale assumptions (ARCHITECTURE.md's generalization
requirement).

The key signal for "parallel content slots" (a card grid, a column row) is
several text shapes of *exactly* the same kind and size that already carry
text: a designer draws one card and duplicates it, so identical geometry means
"one item each", not "one shape".
"""

from __future__ import annotations

from collections import Counter

from ir_schema import AutoShape, Deck, Picture, Shape, Slide, Table, TextBoxShape
from pydantic import BaseModel

_TITLE_KINDS = {"TITLE", "CENTER_TITLE"}
_BODY_KINDS = {"BODY", "SUBTITLE", "OBJECT"}

TextShape = TextBoxShape | AutoShape


def placeholder_kind(shape: Shape) -> str | None:
    """Bare placeholder-type name, e.g. "TITLE" from python-pptx's "TITLE (1)"."""
    if shape.placeholder_type is None:
        return None
    return shape.placeholder_type.split(" (", 1)[0]


def is_title(shape: Shape) -> bool:
    return placeholder_kind(shape) in _TITLE_KINDS


def is_body_placeholder(shape: Shape) -> bool:
    return placeholder_kind(shape) in _BODY_KINDS


def shape_has_text(shape: TextShape) -> bool:
    return any(run.text.strip() for p in shape.paragraphs for run in p.runs)


def repeated_slot_groups(candidates: list[TextShape]) -> list[list[TextShape]]:
    """Groups of >=2 identically-sized, same-kind text shapes, biggest group first.

    Only shapes that already carry text qualify, so decorative same-size
    rectangles (no text) aren't mistaken for content slots. Each group is
    ordered the way a reader scans it: top-to-bottom, then left-to-right.
    """
    by_size: dict[tuple[str, int, int], list[TextShape]] = {}
    for shape in candidates:
        if not shape_has_text(shape):
            continue
        by_size.setdefault((shape.kind, shape.width, shape.height), []).append(shape)
    groups = [g for g in by_size.values() if len(g) >= 2]
    groups.sort(key=lambda g: g[0].width * g[0].height, reverse=True)
    return [sorted(g, key=lambda s: (s.top, s.left)) for g in groups]


class SlotSummary(BaseModel):
    """What one template slide offers to fill, in content terms."""

    has_title: bool = False
    # BODY/SUBTITLE/OBJECT placeholders (free-text areas).
    body_slots: int = 0
    # Size of the largest group of identical text shapes (cards/columns); 0 if none.
    card_slots: int = 0
    has_table: bool = False
    has_picture: bool = False

    @property
    def kind(self) -> str:
        """Coarse structural class, used to group slides and to describe them."""
        if self.card_slots >= 2:
            return "cards"
        if self.has_table:
            return "table"
        if self.body_slots >= 1:
            return "body"
        return "title_only"


def describe_slots(slide: Slide) -> SlotSummary:
    """Structural summary of one template slide."""
    title = False
    body = 0
    fallback: list[TextShape] = []
    table = False
    picture = False

    for shape in slide.shapes:
        if isinstance(shape, Picture):
            picture = True
        elif isinstance(shape, Table):
            table = True
        elif isinstance(shape, (TextBoxShape, AutoShape)):
            if is_title(shape):
                title = True
            elif is_body_placeholder(shape):
                body += 1
            else:
                fallback.append(shape)

    cards = 0
    # Cards only apply when there is no real body placeholder (same precedence
    # the composer uses: body placeholders win, then repeated groups).
    if body == 0:
        groups = repeated_slot_groups(fallback)
        if groups:
            cards = len(groups[0])
        elif any(shape_has_text(s) for s in fallback):
            # A lone free text shape acts as the body (composer's last resort).
            body = 1

    return SlotSummary(
        has_title=title,
        body_slots=body,
        card_slots=cards,
        has_table=table,
        has_picture=picture,
    )


def representative_slots(slides: list[Slide]) -> SlotSummary:
    """The most common structure among a layout's slides (ties -> first seen).

    Instances of one layout can differ (some with a table, some without);
    the majority structure is the honest answer to "what is this layout?".
    """
    summaries = [describe_slots(s) for s in slides]
    counts = Counter(s.model_dump_json() for s in summaries)
    best = counts.most_common(1)[0][0]
    return next(s for s in summaries if s.model_dump_json() == best)


def pick_template_slides(roles: list[str], deck: Deck) -> list[Slide]:
    """The concrete template slide each generated slide will be built on.

    Several template slides can share one layout; repeated roles round-robin
    through them so consecutive same-layout slides don't all look identical.
    Content generation and composition MUST agree on this assignment — the
    text is written for one specific slide's slots — so both call this one
    function. Raises `ValueError` naming any role with no template slide.
    """
    by_role: dict[str, list[Slide]] = {}
    for slide in deck.slides:
        by_role.setdefault(slide.layout_name, []).append(slide)

    cursor: dict[str, int] = {}
    picked: list[Slide] = []
    for role in roles:
        candidates = by_role.get(role)
        if not candidates:
            raise ValueError(
                f"no template slide found for role {role!r} — available roles: {sorted(by_role)}"
            )
        i = cursor.get(role, 0)
        picked.append(candidates[i % len(candidates)])
        cursor[role] = i + 1
    return picked
