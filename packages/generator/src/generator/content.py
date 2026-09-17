"""Outline -> per-slide content, via the `slide-content` skill.

Like `Outline`/`SlideIntent` in `outline.py`, `SlideContent`/`DeckContent` are
pipeline-internal working data between `generator`'s own stages (outline ->
per-slide content) — not part of the final composed slide IR that
`layout`/`export` consume, so they live here rather than in
`packages/ir_schema` (see ARCHITECTURE.md: ir_schema is the shared contract
*between* packages, not a dumping ground for every intermediate shape).
"""

from __future__ import annotations

from design_system import LayoutPattern
from inference import InferenceClient, load_skill
from pydantic import BaseModel, Field, field_validator

from generator.outline import Outline


class SlideContent(BaseModel):
    """Full content for one slide, ready for `layout` to place on its pattern."""

    role: str
    title: str
    bullets: list[str] = Field(default_factory=list)
    body: str | None = None
    table: list[list[str]] | None = None
    image_brief: str | None = None

    @field_validator("bullets", mode="before")
    @classmethod
    def _coerce_null_bullets(cls, value: list[str] | None) -> list[str]:
        # Providers occasionally emit `"bullets": null` for a slide with no
        # bullets instead of `[]`, despite the schema — coerce rather than
        # reject, since it's semantically identical.
        return value if value is not None else []


class DeckContent(BaseModel):
    slides: list[SlideContent] = Field(default_factory=list)


def _patterns_by_name(patterns: list[LayoutPattern]) -> dict[str, LayoutPattern]:
    return {pattern.layout_name: pattern for pattern in patterns}


def _describe_pattern(pattern: LayoutPattern | None) -> str:
    """Summarize a pattern's shape budget for the prompt.

    Only the shape kinds/counts matter here — the geometric bbox ranges are
    `packages/layout`'s concern, not content generation's.
    """
    if pattern is None:
        return "(no matching pattern found in this template — use your judgment)"
    parts = []
    for summary in pattern.shape_summaries:
        parts.append(
            f"{summary.kind} (typically {summary.count_min}-{summary.count_max}, "
            f"avg {summary.count_mean:.1f} per slide)"
        )
    shapes = "; ".join(parts) if parts else "(no shapes recorded for this pattern)"
    return f"available shapes: {shapes}"


def _build_user_prompt(
    brief: str, outline: Outline, patterns: list[LayoutPattern]
) -> str:
    by_name = _patterns_by_name(patterns)
    lines = [f"Brief:\n{brief}\n", "Slides (in order):"]
    for i, slide in enumerate(outline.slides, start=1):
        pattern = by_name.get(slide.role)
        lines.append(
            f"{i}. role: {slide.role}\n"
            f"   intent: {slide.intent}\n"
            f"   summary: {slide.summary}\n"
            f"   {_describe_pattern(pattern)}"
        )
    lines.append(
        '\nRespond with JSON: {"slides": [{"role": ..., "title": ..., '
        '"bullets": [...], "body": ..., "table": [[...], ...], '
        '"image_brief": ...}, ...]}'
    )
    return "\n".join(lines)


def generate_content(
    outline: Outline,
    patterns: list[LayoutPattern],
    brief: str,
    *,
    client: InferenceClient | None = None,
) -> DeckContent:
    """Turn an outline into full per-slide content, one LLM call for the whole deck.

    Each `SlideIntent.role` is matched to its `LayoutPattern` by
    `role == layout_name` so the prompt can tell the model how much content a
    slide of that pattern typically holds (text boxes, tables, pictures) —
    pattern *selection* already happened at the outline stage; this only
    generates content that fits the pattern already chosen.
    """
    skill = load_skill("slide-content")
    inference_client = client or InferenceClient()

    return inference_client.complete_structured(
        model=skill.model,
        system_prompt=skill.prompt,
        user_content=_build_user_prompt(brief, outline, patterns),
        temperature=skill.temperature,
        max_tokens=skill.max_tokens,
        response_model=DeckContent,
    )
