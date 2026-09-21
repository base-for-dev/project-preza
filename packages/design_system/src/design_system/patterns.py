"""IR -> layout patterns: structural/statistical summary per slide-role group.

Slides are grouped by `Slide.layout_name` — the master/layout reference
assigned by whoever built the template. This is the strongest
template-agnostic grouping signal already in the IR: it comes from the
template author, not from us, so grouping by it doesn't encode any
assumption about naming, language, or slide semantics. No attempt is made to
label a pattern's *role* (title vs. content vs. ...) by matching against the
layout name string — that's exactly the kind of hardcoding that breaks on an
unseen template (see ARCHITECTURE.md and this package's docstring). Semantic
role labeling, if wanted, belongs to an LLM skill downstream, not here.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from ir_schema import Deck, Shape
from pydantic import BaseModel

from design_system.slots import SlotSummary, representative_slots


class ShapeSummary(BaseModel):
    """How often, and roughly where, a shape kind appears on this pattern's slides.

    Position/size ranges are normalized to the slide's own width/height
    (0.0-1.0) so they're resolution-independent, and are ranges rather than
    exact values because templates vary shape placement slide to slide even
    within one layout.
    """

    kind: str
    count_min: int
    count_max: int
    count_mean: float
    left_range: tuple[float, float]
    top_range: tuple[float, float]
    right_range: tuple[float, float]
    bottom_range: tuple[float, float]


class LayoutPattern(BaseModel):
    layout_name: str
    slide_count: int
    shape_summaries: list[ShapeSummary]
    # Content-terms structure (cards / body / table / title-only), from the
    # layout's most common slide shape. None only for hand-built patterns.
    slots: SlotSummary | None = None


def _shape_kind_counts(shapes: list[Shape]) -> Counter[str]:
    return Counter(shape.kind for shape in shapes)


def _summarize_kind(
    kind: str,
    per_slide_counts: list[int],
    bboxes: list[tuple[float, float, float, float]],
) -> ShapeSummary:
    lefts = [b[0] for b in bboxes]
    tops = [b[1] for b in bboxes]
    rights = [b[2] for b in bboxes]
    bottoms = [b[3] for b in bboxes]
    return ShapeSummary(
        kind=kind,
        count_min=min(per_slide_counts),
        count_max=max(per_slide_counts),
        count_mean=sum(per_slide_counts) / len(per_slide_counts),
        left_range=(min(lefts), max(lefts)),
        top_range=(min(tops), max(tops)),
        right_range=(min(rights), max(rights)),
        bottom_range=(min(bottoms), max(bottoms)),
    )


def extract_patterns(deck: Deck) -> list[LayoutPattern]:
    """Group the deck's slides by `layout_name` and summarize each group's composition."""
    slides_by_layout: dict[str, list] = defaultdict(list)
    for slide in deck.slides:
        slides_by_layout[slide.layout_name].append(slide)

    width = deck.slide_width or 1
    height = deck.slide_height or 1

    patterns: list[LayoutPattern] = []
    for layout_name, slides in slides_by_layout.items():
        # kind -> per-slide count (0 for slides in this group that lack the kind)
        counts_by_kind: dict[str, list[int]] = defaultdict(list)
        # kind -> list of normalized bboxes, one per shape instance seen
        bboxes_by_kind: dict[str, list[tuple[float, float, float, float]]] = defaultdict(list)

        all_kinds: set[str] = set()
        for slide in slides:
            all_kinds |= {shape.kind for shape in slide.shapes}

        for slide in slides:
            counts = _shape_kind_counts(slide.shapes)
            for kind in all_kinds:
                counts_by_kind[kind].append(counts.get(kind, 0))
            for shape in slide.shapes:
                left = shape.left / width
                top = shape.top / height
                right = (shape.left + shape.width) / width
                bottom = (shape.top + shape.height) / height
                bboxes_by_kind[shape.kind].append((left, top, right, bottom))

        shape_summaries = [
            _summarize_kind(kind, counts_by_kind[kind], bboxes_by_kind[kind])
            for kind in sorted(all_kinds)
            if bboxes_by_kind[kind]
        ]

        patterns.append(
            LayoutPattern(
                layout_name=layout_name,
                slide_count=len(slides),
                shape_summaries=shape_summaries,
                slots=representative_slots(slides),
            )
        )

    return patterns
