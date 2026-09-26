"""Brief -> outline, via the `outline-generation` skill.

An `Outline` is pipeline-internal working data between `generator`'s own stages
(outline -> per-slide content) — it isn't part of the final composed slide IR
that `layout`/`export` consume, so it lives here rather than in
`packages/ir_schema` (see ARCHITECTURE.md: ir_schema is the shared contract
*between* packages, not a dumping ground for every intermediate shape).
"""

from __future__ import annotations

import re

from design_system import LayoutPattern
from inference import InferenceClient, load_skill
from pydantic import BaseModel, Field

from generator.structure import describe_structure
from generator.timing import normalize_seconds


def _pattern_name(pattern: LayoutPattern | str) -> str:
    return pattern.layout_name if isinstance(pattern, LayoutPattern) else pattern


class SlideIntent(BaseModel):
    """One slide's planned role and content, before full content is written."""

    role: str
    intent: str
    summary: str
    # Planned speaking time for this slide. Proposed by the model when a talk
    # length is given, then normalized so the deck sums to it exactly (see
    # `generator.timing.normalize_seconds`); 0 when no length was given.
    seconds: int = 0


class Outline(BaseModel):
    slides: list[SlideIntent] = Field(default_factory=list)


def _catalog_line(pattern: LayoutPattern | str) -> str:
    """One layout-catalog entry: a quoted name, then what it can hold.

    The name is quoted and set off from the description so the model copies
    just the name into `role` — an unquoted "name (n) — description" line got
    echoed back whole, which then failed to match any real layout.
    """
    if isinstance(pattern, str):
        return f'- "{pattern}"'
    purpose = f" — {pattern.description}" if pattern.description else ""
    return (
        f'- "{pattern.layout_name}"  →  {describe_structure(pattern.slots)}{purpose} '
        f"[template has {pattern.slide_count}]"
    )


# Valid values for the optional `mode` parameter — see "Content modes" in
# skills/outline-generation/SKILL.md for what each one means.
MODES = ("briefing", "narrative", "pyramid", "showcase", "instructional")


# How the writer treats the user's own text (Gamma-style `textMode`):
# generate from a topic, condense a long text, or keep the user's wording.
TEXT_MODES = ("generate", "condense", "preserve")
TEXT_MODE_LINES = {
    "condense": (
        "Text mode: condense — the brief is the user's own long text. Summarize it "
        "into the deck: keep its facts and argument, cut detail; add nothing new."
    ),
    "preserve": (
        "Text mode: preserve — the brief is the user's finished text. Keep its "
        "wording and order; only split it across slides and trim what can't fit. "
        "Do not rephrase, embellish, or add points."
    ),
}

_SECTION_BREAK = re.compile(r"^\s*-{3,}\s*$", re.MULTILINE)


def split_sections(text: str) -> list[str]:
    """The user's own slide breaks: parts of `text` separated by "---" lines.

    Returns [] when the text has no breaks (then the outline splits the
    content itself), else every non-empty part, in order — one slide each.
    """
    parts = [p.strip() for p in _SECTION_BREAK.split(text)]
    parts = [p for p in parts if p]
    return parts if len(parts) >= 2 else []


def _build_user_prompt(
    brief: str,
    slide_count: int,
    available_patterns: list[LayoutPattern | str],
    mode: str | None,
    brand: str | None = None,
    duration_seconds: int | None = None,
    sections: list[str] | None = None,
    text_mode: str | None = None,
) -> str:
    catalog = "\n".join(_catalog_line(p) for p in available_patterns) or "(none provided)"
    if mode:
        mode_line = f"Deck mode: {mode} — follow that mode's rules exactly."
    else:
        mode_line = (
            "Deck mode: not specified — infer the single best-fit mode from "
            f"the brief's own wording and audience (one of {', '.join(MODES)}), "
            "and follow that mode's rules consistently across the outline."
        )
    brand_block = f"Brand guide (use its names and voice):\n{brand}\n\n" if brand else ""
    if duration_seconds:
        timing_line = (
            f"Talk length: {duration_seconds} seconds spoken over the slides. Give each "
            "slide a `seconds` value — how long the speaker stays on it — summing to "
            f"{duration_seconds}. Opening and closing slides are short; the slides "
            "carrying the core argument get the most time.\n\n"
        )
        seconds_field = ', "seconds": ...'
    else:
        timing_line = ""
        seconds_field = ""
    sections_block = ""
    if sections:
        listed = "\n".join(f"{i}. {s}" for i, s in enumerate(sections, start=1))
        sections_block = (
            f"The user split the deck themselves: exactly {len(sections)} slides, slide N "
            f"covers section N and nothing else, in this order:\n{listed}\n\n"
        )
    text_mode_block = f"{TEXT_MODE_LINES[text_mode]}\n\n" if text_mode in TEXT_MODE_LINES else ""
    return (
        f"Brief:\n{brief}\n\n"
        f"{sections_block}"
        f"{text_mode_block}"
        f"{brand_block}"
        f"Target slide count: {slide_count}\n\n"
        f"{timing_line}"
        f"{mode_line}\n\n"
        "Available layouts (each `role` must be one of these names, copied "
        f"exactly):\n{catalog}\n\n"
        'Respond with JSON: {"slides": [{"role": ..., "intent": ..., "summary": ...'
        f"{seconds_field}}}, ...]}}"
    )


def generate_outline(
    brief: str,
    slide_count: int,
    available_patterns: list[LayoutPattern] | list[str],
    *,
    mode: str | None = None,
    brand: str | None = None,
    duration_seconds: int | None = None,
    sections: list[str] | None = None,
    text_mode: str | None = None,
    client: InferenceClient | None = None,
) -> Outline:
    """Turn a free-text brief into an ordered list of slide intents.

    `available_patterns` is the set of slide-role/layout patterns the outline
    may draw on — either `design_system.LayoutPattern`s (from
    `extract_design_system`) or plain layout-name strings. Only each
    pattern's name goes into the prompt; the geometric/compositional summary
    a `LayoutPattern` carries is `packages/layout`'s job, not the outline
    stage's.

    `mode` — one of `MODES` (briefing/narrative/pyramid/showcase/
    instructional), or `None` to let the model infer it from the brief.

    `brand` — a brand pack's prompt block (`BrandContext.prompt_text()`).
    `duration_seconds` — the talk length; each slide then gets a `seconds`
    share, normalized to sum to it exactly.
    `sections` — the user's own slide breaks (see `split_sections`): one
    slide per section, in order. `text_mode` — see `TEXT_MODES`.
    """
    if sections:
        slide_count = len(sections)
    skill = load_skill("outline-generation")
    inference_client = client or InferenceClient()
    available_patterns = _fillable_only(available_patterns)

    outline = inference_client.complete_structured(
        model=skill.model,
        system_prompt=skill.prompt,
        user_content=_build_user_prompt(
            brief, slide_count, available_patterns, mode, brand, duration_seconds,
            sections, text_mode,
        ),
        temperature=skill.temperature,
        max_tokens=skill.max_tokens,
        fallback_models=skill.fallback_models,
        timeout=skill.timeout,
        response_model=Outline,
    )

    return finalize_outline(outline, available_patterns, duration_seconds)


def finalize_outline(
    outline: Outline,
    available_patterns: list[LayoutPattern] | list[str],
    duration_seconds: int | None = None,
) -> Outline:
    """Make an outline safe to compose: real roles, a cover first, exact timing.

    Applied to the model's outline and equally to one the user edited before
    generation (Gamma-style outline review), so a hand-typed role or a
    deleted slide can't break composition or the talk's length.
    """
    available_patterns = _fillable_only(available_patterns)
    # The prompt lists the valid roles, but nothing stops the model from
    # answering with one outside that set (seen on the free-tier model:
    # `role: "Сравнение"` for a template with no such layout) — downstream
    # `layout.compose_deck` matches role to template `layout_name` exactly
    # and raises on a miss. Clamp any hallucinated role to the first
    # available pattern rather than letting the whole pipeline crash — same
    # "pick a deterministic default" discipline as the rest of the codebase,
    # not a semantic guess at which pattern was "meant".
    valid_names = [_pattern_name(p) for p in available_patterns]
    if valid_names:
        for slide in outline.slides:
            slide.role = _resolve_role(slide.role, valid_names)

    _open_on_the_cover(outline, available_patterns)

    if duration_seconds and outline.slides:
        shares = normalize_seconds([s.seconds for s in outline.slides], duration_seconds)
        for slide, seconds in zip(outline.slides, shares, strict=True):
            slide.seconds = seconds

    return outline


def _fillable_only(patterns: list[LayoutPattern] | list[str]) -> list[LayoutPattern] | list[str]:
    """Drop layouts with nowhere to put text (a bare picture, an empty divider).

    Offering one lets the model choose it, and the slide then comes out blank
    (confirmed live: a deck opening and closing on an empty "picture with
    caption" layout). Falls back to the full list if nothing would remain.
    """

    def fillable(p: LayoutPattern | str) -> bool:
        if not isinstance(p, LayoutPattern) or p.slots is None:
            return True
        s = p.slots
        return s.has_title or s.body_slots > 0 or s.card_slots > 0 or s.has_table

    kept = [p for p in patterns if fillable(p)]
    return kept or patterns  # type: ignore[return-value]


# The first this-many *title-capable* layouts of the template (in its own
# order) count as cover-like: the template's order is its designer's intent.
_COVER_WINDOW = 2


def _open_on_the_cover(outline: Outline, patterns: list[LayoutPattern] | list[str]) -> None:
    """Make the deck open on one of the template's cover layouts.

    The prompt tells the writer to open strongly, but a model regularly picks a
    sparse content layout for slide 1 (confirmed live: a near-empty white
    "Контент" slide as the opening). The template's first slides are its cover;
    if slide 1 is not on one of those layouts, it is moved to the template's
    own first one. Layouts that cannot carry a title (a bare picture slide) or
    that are card/table layouts are never covers. Only applies when layout
    positions and slot structure are known.
    """
    candidates = sorted(
        (
            p
            for p in patterns
            if isinstance(p, LayoutPattern)
            and p.slots is not None
            and p.slots.has_title
            and p.slots.kind in ("title_only", "body")
        ),
        key=lambda p: p.first_slide_index,
    )
    if not candidates or not outline.slides:
        return
    covers = {p.layout_name for p in candidates[:_COVER_WINDOW]}
    if outline.slides[0].role not in covers:
        outline.slides[0].role = candidates[0].layout_name


def _resolve_role(role: str, valid_names: list[str]) -> str:
    """Map a model-emitted `role` onto a real layout name.

    Exact match wins. Otherwise recover a name the model decorated (quotes,
    or the catalog description echoed after it): the *longest* valid name that
    the emitted text starts with or contains — longest so "1_Контент" is not
    mistaken for "11_Контент"'s prefix. Only if nothing is recognisable fall
    back to the first layout, so a genuinely hallucinated role can't crash
    `layout.compose_deck` (which matches roles exactly).
    """
    if role in valid_names:
        return role
    cleaned = role.strip().strip("\"'`")
    if cleaned in valid_names:
        return cleaned
    by_length = sorted(valid_names, key=len, reverse=True)
    for name in by_length:
        if cleaned.startswith(name):
            return name
    for name in by_length:
        if name in cleaned:
            return name
    return valid_names[0]
