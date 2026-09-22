"""Outline -> per-slide content, via the `slide-content` skill.

Like `Outline`/`SlideIntent` in `outline.py`, `SlideContent`/`DeckContent` are
pipeline-internal working data between `generator`'s own stages (outline ->
per-slide content) — not part of the final composed slide IR that
`layout`/`export` consume, so they live here rather than in
`packages/ir_schema` (see ARCHITECTURE.md: ir_schema is the shared contract
*between* packages, not a dumping ground for every intermediate shape).
"""

from __future__ import annotations

from design_system import LayoutPattern, SlotSummary, describe_slots
from inference import InferenceClient, load_skill
from ir_schema import Slide
from pydantic import BaseModel, Field, field_validator

from generator.outline import Outline
from generator.structure import describe_structure


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


def _slide_budget(slots: SlotSummary | None) -> str:
    """Content budget for one slide, from its slot structure.

    Ideally `slots` describe the exact template slide the composer will use
    (see `design_system.pick_template_slides`), so "3 cards" here means the
    slide this text lands on really has 3; the layout's majority structure is
    the fallback when no specific slide was pinned.
    """
    if slots is None:
        return "structure unknown (use judgment)"
    lines = [f"structure: {describe_structure(slots)}"]
    if slots.kind == "cards":
        lines.append(
            f'fill: "bullets" must have EXACTLY {slots.card_slots} items, one per card, '
            "each a short self-contained point (max ~8 words); body must be null"
        )
    elif slots.kind == "table":
        lines.append('fill: put the data in "table"; bullets empty; body null')
    elif slots.kind == "body":
        lines.append('fill: "bullets" (2-5 items) OR "body" (one short paragraph), not both')
    else:
        lines.append('fill: title only — bullets empty, body null, table null')
    lines.append(
        f'"table": {"allowed" if slots.has_table else "must be null"}; '
        f'"image_brief": {"allowed" if slots.has_picture else "must be null"}'
    )
    return "\n   ".join(lines)


_DENSITY_LINES = {
    "compact": (
        "Target density: compact — write as little as each slide's point "
        "needs. Prefer 2-3 short bullets, or a single short sentence, over "
        "filling every slot a layout allows."
    ),
    "standard": (
        "Target density: standard — a normal, balanced amount of content per "
        "slide. Neither stripped down nor maximal."
    ),
    "detailed": (
        "Target density: detailed — elaborate fully. Use the fuller end of "
        "each slide's allowed bullet/body range, and prefer a `body` "
        "paragraph over a short bullet list wherever `fill:` allows both."
    ),
}


def _build_user_prompt(
    brief: str,
    outline: Outline,
    slot_summaries: list[SlotSummary | None],
    density: str | None = None,
) -> str:
    lines = [f"Brief:\n{brief}\n"]
    density_line = _DENSITY_LINES.get(density or "")
    if density_line:
        lines.append(f"{density_line}\n")
    lines.append("Slides (in order):")
    for i, (slide, slots) in enumerate(zip(outline.slides, slot_summaries, strict=True), start=1):
        budget = _slide_budget(slots)
        lines.append(
            f"{i}. role: {slide.role}\n"
            f"   intent: {slide.intent}\n"
            f"   summary: {slide.summary}\n"
            f"   {budget}"
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
    template_slides: list[Slide] | None = None,
    density: str | None = None,
    client: InferenceClient | None = None,
) -> DeckContent:
    """Turn an outline into full per-slide content, one LLM call for the whole deck.

    Layout *selection* already happened at the outline stage; this writes
    content that fits the slide chosen. `template_slides` (one per outline
    slide, from `design_system.pick_template_slides`) pins each slide to the
    exact template slide it will be composed on, so the prompt states that
    slide's real slot counts; without it, each slide's layout majority
    structure (`LayoutPattern.slots`) is used.

    `density` — "compact" / "standard" / "detailed" (see the leading question
    the UI asks when a brief doesn't say), or `None` for the skill's own
    default. Only nudges free-form ("body"-kind) slides' fill amount — a
    card slide's exact card count is structural and never changes with it.
    """
    skill = load_skill("slide-content")
    inference_client = client or InferenceClient()

    if template_slides is not None:
        slot_summaries: list[SlotSummary | None] = [describe_slots(s) for s in template_slides]
    else:
        by_name = {p.layout_name: p.slots for p in patterns}
        slot_summaries = [by_name.get(s.role) for s in outline.slides]

    return inference_client.complete_structured(
        model=skill.model,
        system_prompt=skill.prompt,
        user_content=_build_user_prompt(brief, outline, slot_summaries, density),
        temperature=skill.temperature,
        max_tokens=skill.max_tokens,
        response_model=DeckContent,
    )
