"""Outline -> per-slide content, via the `slide-content` skill.

Like `Outline`/`SlideIntent` in `outline.py`, `SlideContent`/`DeckContent` are
pipeline-internal working data between `generator`'s own stages (outline ->
per-slide content) — not part of the final composed slide IR that
`layout`/`export` consume, so they live here rather than in
`packages/ir_schema` (see ARCHITECTURE.md: ir_schema is the shared contract
*between* packages, not a dumping ground for every intermediate shape).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from design_system import LayoutPattern, SlotSummary, describe_slots, figures
from inference import InferenceClient, load_skill
from ir_schema import Slide
from pydantic import BaseModel, Field, field_validator

from generator.outline import Outline
from generator.structure import describe_structure
from generator.timing import DEFAULT_SLIDE_SECONDS, words_for

# Concurrent content calls per deck, each writing a contiguous group of
# slides. Parallel groups cut latency to roughly one group's completion;
# capping the count keeps a generation to a handful of requests — free-tier
# accounts get ~50 free-model requests per day, not per minute.
CONTENT_CALLS = 3


class SlideContent(BaseModel):
    """Full content for one slide, ready for `layout` to place on its pattern."""

    role: str
    title: str
    bullets: list[str] = Field(default_factory=list)
    body: str | None = None
    table: list[list[str]] | None = None
    image_brief: str | None = None
    # 2-4 English keywords for stock-photo search (see packages/images) —
    # separate from `image_brief`, which is written in the brief's language
    # for humans; photo search works far better on short English terms.
    image_query: str | None = None
    # What the speaker says over this slide, in the brief's language, sized
    # to the slide's share of the talk length.
    speaker_notes: str | None = None

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
        lines.append(_body_fill_line(slots))
    else:
        lines.append("fill: title only — bullets empty, body null, table null")
    lines.append(
        f'"table": {"allowed" if slots.has_table else "must be null"}; '
        f'"image_brief": {"required" if slots.has_picture else "must be null"}; '
        f'"image_query": {"required" if slots.has_picture else "must be null"}'
    )
    return "\n   ".join(lines)


def _body_fill_line(slots: SlotSummary) -> str:
    """Fill rule for a free-text slide, sized to the slot's real capacity."""
    rows, chars = slots.body_lines, slots.body_chars_per_line
    if rows is None or chars is None:
        return 'fill: "bullets" (2-5 items) OR "body" (one short paragraph), not both'
    # A bullet wraps, so the number of bullets that fit is bounded by lines
    # available at ~2 lines per bullet at most; never demand fewer than 1.
    max_bullets = max(1, min(5, rows))
    per_item = chars * (2 if rows >= 4 else 1)
    if max_bullets == 1:
        return (
            f"fill: the text area is small (~{rows} line{'s' if rows > 1 else ''} of ~{chars} "
            f'chars) — "bullets" with EXACTLY 1 item of at most {per_item} characters, '
            'or "body" of at most that length; not both'
        )
    return (
        f'fill: "bullets" ({min(2, max_bullets)}-{max_bullets} items, each at most '
        f'{per_item} characters) OR "body" (at most {rows * chars} characters), not both'
    )


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


# Models write notes well short of any stated length — measured live at
# ~75% of the target even when it's phrased as a floor. Asking for this much
# more lands the actual notes near the real speaking budget.
NOTES_UNDERSHOOT = 1.3


def _notes_line(seconds: int) -> str:
    spoken = seconds or DEFAULT_SLIDE_SECONDS
    words = round(words_for(spoken) * NOTES_UNDERSHOOT)
    return (
        f'"speaker_notes": {words} words, at least {round(words * 0.9)} '
        f"(spoken over ~{spoken} s)"
    )


def _build_user_prompt(
    brief: str,
    outline: Outline,
    slot_summaries: list[SlotSummary | None],
    density: str | None = None,
    brand: str | None = None,
    only_slides: list[int] | None = None,
) -> str:
    """The content prompt for the whole deck, or for a group of its slides.

    With `only_slides` (0-based positions), the whole outline is still
    listed — so the writer knows what every other slide covers and doesn't
    repeat it — but only those slides get fill rules, and the reply holds
    exactly those slides, in order.
    """
    lines = [f"Brief:\n{brief}\n"]
    if brand:
        lines.append(f"Brand guide (use its names and voice):\n{brand}\n")
    density_line = _DENSITY_LINES.get(density or "")
    if density_line:
        lines.append(f"{density_line}\n")
    lines.append("Slides (in order):")
    for i, (slide, slots) in enumerate(zip(outline.slides, slot_summaries, strict=True)):
        entry = f"{i + 1}. role: {slide.role}\n   intent: {slide.intent}\n   summary: {slide.summary}"
        if only_slides is None or i in only_slides:
            entry += f"\n   {_slide_budget(slots)}\n   {_notes_line(slide.seconds)}"
        lines.append(entry)
    shape = (
        '{"role": ..., "title": ..., "bullets": [...], "body": ..., '
        '"table": [[...], ...], "image_brief": ..., "image_query": ..., '
        '"speaker_notes": ...}'
    )
    if only_slides is None:
        lines.append(f'\nRespond with JSON: {{"slides": [{shape}, ...]}}')
    else:
        numbers = ", ".join(str(i + 1) for i in only_slides)
        lines.append(
            f"\nWrite ONLY slides {numbers} of {len(outline.slides)}. The other slides "
            "are listed so you know what they cover — don't repeat their points.\n"
            f'Respond with JSON: {{"slides": [{shape}, ...]}} — exactly '
            f"{len(only_slides)} slide(s), in that order."
        )
    return "\n".join(lines)


def generate_content(
    outline: Outline,
    patterns: list[LayoutPattern],
    brief: str,
    *,
    template_slides: list[Slide] | None = None,
    density: str | None = None,
    brand: str | None = None,
    parallel: bool = True,
    client: InferenceClient | None = None,
) -> DeckContent:
    """Turn an outline into full per-slide content plus speaker notes.

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

    `parallel` (default) splits the deck into `CONTENT_CALLS` contiguous
    groups written by concurrent LLM calls — each reply is a third of the
    deck, so the whole lands in roughly one group's latency instead of one
    huge sequential completion; that keeps generation inside the 5-minute
    budget on a slow model. A failed group is retried once.
    `parallel=False` is the single whole-deck call.
    """
    skill = load_skill("slide-content")
    inference_client = client or InferenceClient()

    if template_slides is not None:
        slot_summaries: list[SlotSummary | None] = [describe_slots(s) for s in template_slides]
    else:
        by_name = {p.layout_name: p.slots for p in patterns}
        slot_summaries = [by_name.get(s.role) for s in outline.slides]

    def call(only_slides: list[int] | None, extra: str = "") -> DeckContent:
        prompt = _build_user_prompt(brief, outline, slot_summaries, density, brand, only_slides)
        return inference_client.complete_structured(
            model=skill.model,
            system_prompt=skill.prompt,
            user_content=prompt + extra,
            temperature=skill.temperature,
            max_tokens=skill.max_tokens,
            fallback_models=skill.fallback_models,
            timeout=skill.timeout,
            response_model=DeckContent,
        )

    def grounded(only_slides: list[int] | None, write) -> DeckContent:
        """Write, then one corrective pass if figures not in the brief appear.

        The prompt's "never invent facts" rule is not reliable on its own; one
        corrective pass naming the exact offending figures is. Slide numbers
        in the feedback are the deck's own (1-based), so they match the
        prompt's slide list in both whole-deck and group mode.
        """
        content = write("")
        numbers = only_slides if only_slides is not None else range(len(content.slides))
        invented = _ungrounded_by_slide(content, brief, [n + 1 for n in numbers])
        if not invented:
            return content
        feedback = "\n".join(f"- slide {i}: {', '.join(sorted(f))}" for i, f in invented.items())
        retry = write(
            f"\n\nYour previous draft used figures that are NOT in the brief:\n"
            f"{feedback}\nRewrite the same slides with the same structure, but express "
            "every one of those claims qualitatively in words — no numbers, percentages, or "
            "durations the brief does not itself state."
        )
        retry_invented = _ungrounded_by_slide(retry, brief, [n + 1 for n in numbers])
        if len(retry.slides) == len(content.slides) and sum(
            map(len, retry_invented.values())
        ) <= sum(map(len, invented.values())):
            return retry
        return content

    if not parallel:
        return grounded(None, lambda extra: call(None, extra))

    def group(positions: list[int]) -> list[SlideContent]:
        def write(extra: str) -> DeckContent:
            last_error: Exception | None = None
            for _ in range(2):
                try:
                    result = call(positions, extra)
                    if len(result.slides) == len(positions):
                        for slide, i in zip(result.slides, positions, strict=True):
                            # The role is structural (it picks the template
                            # slide); never let the writer change it.
                            slide.role = outline.slides[i].role
                        return result
                    last_error = ValueError(
                        f"slides {positions}: got {len(result.slides)} slides back"
                    )
                except Exception as exc:
                    last_error = exc
            raise last_error or RuntimeError(f"slides {positions} failed")

        return grounded(positions, write).slides

    count = len(outline.slides)
    size = max(1, -(-count // CONTENT_CALLS))
    groups = [list(range(start, min(start + size, count))) for start in range(0, count, size)]
    with ThreadPoolExecutor(max_workers=max(1, len(groups))) as pool:
        written = list(pool.map(group, groups))
    return DeckContent(slides=[slide for chunk in written for slide in chunk])


def _slide_text(slide: SlideContent) -> str:
    # Notes are included: a figure the speaker says aloud is as much a claim
    # to the audience as one printed on the slide.
    parts = [slide.title, *slide.bullets, slide.body or "", slide.speaker_notes or ""]
    parts += [cell for row in slide.table or [] for cell in row]
    return " ".join(parts)


def _ungrounded_by_slide(
    content: DeckContent, brief: str, numbers: list[int] | None = None
) -> dict[int, set[str]]:
    """Slide number (1-based, in the deck) -> figures it states but the brief never does."""
    allowed = figures(brief)
    numbers = numbers or list(range(1, len(content.slides) + 1))
    out: dict[int, set[str]] = {}
    for number, slide in zip(numbers, content.slides, strict=False):
        bad = figures(_slide_text(slide)) - allowed
        if bad:
            out[number] = bad
    return out
