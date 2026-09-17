"""Brief -> outline, via the `outline-generation` skill.

An `Outline` is pipeline-internal working data between `generator`'s own stages
(outline -> per-slide content) — it isn't part of the final composed slide IR
that `layout`/`export` consume, so it lives here rather than in
`packages/ir_schema` (see ARCHITECTURE.md: ir_schema is the shared contract
*between* packages, not a dumping ground for every intermediate shape).
"""

from __future__ import annotations

from design_system import LayoutPattern
from inference import InferenceClient, load_skill
from pydantic import BaseModel, Field


def _pattern_name(pattern: LayoutPattern | str) -> str:
    return pattern.layout_name if isinstance(pattern, LayoutPattern) else pattern


class SlideIntent(BaseModel):
    """One slide's planned role and content, before full content is written."""

    role: str
    intent: str
    summary: str


class Outline(BaseModel):
    slides: list[SlideIntent] = Field(default_factory=list)


def _build_user_prompt(
    brief: str, slide_count: int, available_patterns: list[LayoutPattern | str]
) -> str:
    names = [_pattern_name(p) for p in available_patterns]
    patterns = ", ".join(names) if names else "(none provided)"
    return (
        f"Brief:\n{brief}\n\n"
        f"Target slide count: {slide_count}\n\n"
        f"Available slide-role patterns: {patterns}\n\n"
        'Respond with JSON: {"slides": [{"role": ..., "intent": ..., "summary": ...}, ...]}'
    )


def generate_outline(
    brief: str,
    slide_count: int,
    available_patterns: list[LayoutPattern] | list[str],
    *,
    client: InferenceClient | None = None,
) -> Outline:
    """Turn a free-text brief into an ordered list of slide intents.

    `available_patterns` is the set of slide-role/layout patterns the outline
    may draw on — either `design_system.LayoutPattern`s (from
    `extract_design_system`) or plain layout-name strings. Only each
    pattern's name goes into the prompt; the geometric/compositional summary
    a `LayoutPattern` carries is `packages/layout`'s job, not the outline
    stage's.
    """
    skill = load_skill("outline-generation")
    inference_client = client or InferenceClient()

    return inference_client.complete_structured(
        model=skill.model,
        system_prompt=skill.prompt,
        user_content=_build_user_prompt(brief, slide_count, available_patterns),
        temperature=skill.temperature,
        max_tokens=skill.max_tokens,
        response_model=Outline,
    )
