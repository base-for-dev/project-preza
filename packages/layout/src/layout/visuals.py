"""Put a writer's chart or diagram on a composed slide.

The visual takes the place of the slide's photo frame, or failing that of its
text area — the two slots content generation is told a visual may replace (see
`generator.content.can_hold_visual`). Nothing is placed anywhere else: a slide
with neither slot keeps its text, and the visual's points become bullets so no
content is lost.
"""

from __future__ import annotations

from dataclasses import dataclass

from design_system import is_body_placeholder, is_non_content_shape, is_title
from generator.content import SlideContent
from ir_schema import (
    AutoShape,
    ChartShape,
    DiagramShape,
    PassthroughShape,
    Picture,
    Shape,
    Slide,
    TextBoxShape,
)

# A photo frame must be at least this share of the slide (and this share of each
# side) to be a place for a visual — smaller pictures are logos and avatars.
MIN_FRAME_AREA_SHARE = 0.08
MIN_FRAME_SIDE_SHARE = 0.2
# Text areas smaller than this share of the slide are labels, not a text area.
MIN_TEXT_AREA_SHARE = 0.12
# Inset kept between the visual and the edge of the space it takes.
INSET_SHARE = 0.02
# Preferred size of text inside a visual, and the range the template's scale may give.
PREFERRED_PT = 16.0
MIN_PT, MAX_PT = 12.0, 24.0


@dataclass(frozen=True)
class Look:
    """What a drawn visual borrows from the template: its font and a type-scale size."""

    slide_width: int
    slide_height: int
    font_name: str | None
    text_pt: float

    @classmethod
    def from_template(
        cls, slide_width: int, slide_height: int, fonts: list[str], type_scale: list[float]
    ) -> Look:
        sizes = [s for s in type_scale if MIN_PT <= s <= MAX_PT]
        pt = min(sizes, key=lambda s: abs(s - PREFERRED_PT)) if sizes else PREFERRED_PT
        return cls(slide_width, slide_height, fonts[0] if fonts else None, pt)


def has_template_chart(slide: Slide) -> bool:
    return any(isinstance(s, PassthroughShape) and s.is_chart for s in slide.shapes)


def _bounds(shapes: list[Shape]) -> tuple[int, int, int, int]:
    left = min(s.left for s in shapes)
    top = min(s.top for s in shapes)
    return (
        left,
        top,
        max(s.left + s.width for s in shapes) - left,
        max(s.top + s.height for s in shapes) - top,
    )


def _slot(slide: Slide, look: Look) -> list[Shape] | None:
    """The shapes a visual replaces: the largest photo frame, else the text area."""
    area = look.slide_width * look.slide_height
    frames = [
        s
        for s in slide.shapes
        if isinstance(s, Picture)
        and not s.is_background
        and s.width * s.height >= MIN_FRAME_AREA_SHARE * area
        and s.width >= MIN_FRAME_SIDE_SHARE * look.slide_width
        and s.height >= MIN_FRAME_SIDE_SHARE * look.slide_height
    ]
    if frames:
        return [max(frames, key=lambda s: s.width * s.height)]
    texts = [
        s
        for s in slide.shapes
        if isinstance(s, (TextBoxShape, AutoShape))
        and not is_title(s)
        and not is_non_content_shape(s)
    ]
    body = [s for s in texts if is_body_placeholder(s)]
    if not body and texts:
        body = [max(texts, key=lambda s: s.width * s.height)]
    if body and _bounds(body)[2] * _bounds(body)[3] >= MIN_TEXT_AREA_SHARE * area:
        return body
    return None


def _as_bullets(content: SlideContent) -> list[str]:
    """A visual's points as plain bullets, for a slide with nowhere to draw it."""
    if content.diagram is not None:
        return [f"{i.label} — {i.detail}" if i.detail else i.label for i in content.diagram.items]
    return []


def without_homeless_visual(slide: Slide, content: SlideContent, look: Look) -> SlideContent:
    """`content`, with a visual that has no slot on `slide` turned into plain bullets.

    Run before the slide's text is filled, so a diagram's points still reach the
    slide (a chart has no text to fall back on and is simply dropped).
    """
    if (content.chart is None and content.diagram is None) or _slot(slide, look) is not None:
        return content
    return content.model_copy(
        update={"chart": None, "diagram": None, "bullets": content.bullets or _as_bullets(content)}
    )


def place_visual(slide: Slide, content: SlideContent, look: Look, *, chart_filled: bool) -> None:
    """Draw `content`'s chart or diagram on `slide` in place of its photo frame or text area.

    `chart_filled`: the template's own chart already carries the writer's numbers
    (see `compose._fill_or_drop_charts`), so no second chart is drawn.
    """
    if content.chart is None and content.diagram is None:
        return
    if content.chart is not None and chart_filled:
        return
    slot = _slot(slide, look)
    if slot is None:
        return
    left, top, width, height = _bounds(slot)
    pad_x, pad_y = int(width * INSET_SHARE), int(height * INSET_SHARE)
    box = {
        "left": left + pad_x,
        "top": top + pad_y,
        "width": width - 2 * pad_x,
        "height": height - 2 * pad_y,
    }
    taken = {s.shape_id for s in slot}
    z = max(s.z_order for s in slide.shapes) + 1 if slide.shapes else 0
    shape_id = max((s.shape_id for s in slide.shapes), default=0) + 1
    slide.shapes = [s for s in slide.shapes if s.shape_id not in taken]
    common = {
        "shape_id": shape_id,
        "z_order": z,
        "font_name": look.font_name,
        "font_size_pt": look.text_pt,
        **box,
    }
    if content.chart is not None:
        chart = content.chart
        slide.shapes.append(
            ChartShape(
                name="Chart",
                chart_type=chart.chart_type,
                title=chart.title,
                unit=chart.unit,
                category_label=chart.category_label,
                categories=chart.categories,
                series=chart.series,
                **common,
            )
        )
    elif content.diagram is not None:
        slide.shapes.append(
            DiagramShape(
                name="Diagram",
                diagram_type=content.diagram.diagram_type,
                items=content.diagram.items,
                **common,
            )
        )


__all__ = ["Look", "has_template_chart", "place_visual", "without_homeless_visual"]
