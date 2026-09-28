"""Outline -> per-slide content, via the `slide-content` skill.

Like `Outline`/`SlideIntent` in `outline.py`, `SlideContent`/`DeckContent` are
pipeline-internal working data between `generator`'s own stages (outline ->
per-slide content) — not part of the final composed slide IR that
`layout`/`export` consume, so they live here rather than in
`packages/ir_schema` (see ARCHITECTURE.md: ir_schema is the shared contract
*between* packages, not a dumping ground for every intermediate shape).
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor

from design_system import LayoutPattern, SlotSummary, describe_slots, figures
from inference import DeadlineExceeded, InferenceClient, QuotaExhausted, load_skill
from ir_schema import Slide
from pydantic import BaseModel, Field, field_validator

from generator.language import deck_language, is_in, language_line
from generator.outline import TEXT_MODE_LINES, Outline
from generator.structure import describe_structure
from generator.textfix import Fix, rewrite_strings
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
    # 1-based number of one of the user's own images (see `user_images` in
    # `generate_content`) to show in this slide's photo frame, or None.
    user_image: int | None = None
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
    if slots.title_chars is not None:
        lines.append(f"title: at most {slots.title_chars} characters (the title area is small)")
    if slots.kind == "cards" and slots.card_fields == 2:
        heading = f"≤ {slots.card_heading_chars} chars" if slots.card_heading_chars else "short"
        lines.append(
            f'fill: "bullets" must have EXACTLY {slots.card_slots} items, one per card, each '
            f'written as "Heading — text": a heading ({heading}, e.g. a step name, a number '
            f"with its unit, a person's name) then \" — \" then its text "
            f"({_card_size_hint(slots)}); body must be null"
        )
    elif slots.kind == "cards":
        lines.append(
            f'fill: "bullets" must have EXACTLY {slots.card_slots} items, one per card, '
            f"each a short self-contained point ({_card_size_hint(slots)}); body must be null"
        )
    elif slots.kind == "table":
        lines.append('fill: put the data in "table"; bullets empty; body null')
    elif slots.kind == "body":
        lines.append(_body_fill_line(slots))
    else:
        lines.append(
            "fill: title only — bullets empty, body null"
            + ("" if slots.has_chart else ", table null")
        )
    if slots.has_chart and not slots.has_table:
        lines.append(
            'chart: "table" feeds the slide\'s chart — header row = [label, series names...], '
            "then one row per category = [category, numbers...]; ONLY numbers stated in the "
            'brief. No such numbers -> "table": null and the chart is removed'
        )
    # A table slot left empty would keep the template's own sample rows, so
    # a slide with a table must get one; a chart alone may be dropped.
    table_rule = "required" if slots.has_table else "allowed" if slots.has_chart else "must be null"
    lines.append(
        f'"table": {table_rule}; '
        f'"image_brief": {"required" if slots.has_picture else "must be null"}; '
        f'"image_query": {"required" if slots.has_picture else "must be null"}'
    )
    return "\n   ".join(lines)


# Card boxes up to this many characters are heading-sized; bigger ones are
# designed for a sentence, and a 5-word card leaves them visibly empty
# (Canva-style packs have 300-character cards).
CARD_HEADING_CHARS = 60
CARD_CHARS_CEILING = 200


def _card_size_hint(slots: SlotSummary) -> str:
    if slots.card_chars is None:
        return "max ~8 words"
    if slots.card_chars <= CARD_HEADING_CHARS:
        return f"at most {slots.card_chars} characters — the card is small — and max ~8 words"
    # Still ≤ 15 words: the audit's per-paragraph readability limit holds
    # however big the box is.
    return (
        f"one full sentence of 8-15 words, at most {min(slots.card_chars, CARD_CHARS_CEILING)} "
        "characters — the card is large, a bare heading would leave it empty"
    )


def _body_limits(slots: SlotSummary) -> tuple[int, int, int] | None:
    """(max bullets, max chars per bullet, max chars of a `body`) for a free-text slot."""
    rows, chars = slots.body_lines, slots.body_chars_per_line
    if rows is None or chars is None:
        return None
    # A bullet wraps, so the number of bullets that fit is bounded by the
    # lines available; never demand fewer than 1.
    return (
        max(1, min(5, rows)),
        chars * (2 if rows >= 4 else 1),
        slots.body_text_chars or rows * chars,
    )


def _body_fill_line(slots: SlotSummary) -> str:
    """Fill rule for a free-text slide, sized to the slot's real capacity."""
    limits = _body_limits(slots)
    if limits is None:
        return 'fill: "bullets" (2-5 items) OR "body" (one short paragraph), not both'
    max_bullets, per_item, body_total = limits
    rows, chars = slots.body_lines, slots.body_chars_per_line
    if max_bullets == 1:
        return (
            f"fill: the text area is small (~{rows} line{'s' if rows and rows > 1 else ''} of "
            f'~{chars} chars) — "bullets" with EXACTLY 1 item of at most {per_item} characters, '
            'or "body" of at most that length; not both'
        )
    return (
        f'fill: "bullets" ({min(2, max_bullets)}-{max_bullets} items, each at most '
        f'{per_item} characters) OR "body" (at most {body_total} characters), not both'
    )


_MAX_CORRECTIONS = 2

# Writers overshoot a stated character limit a little; only flag real overruns.
_LENGTH_SLACK = 1.25
_MAX_WORDS_PER_BULLET = 15


def _length_problems(slide: SlideContent, slots: SlotSummary | None) -> list[str]:
    """Ways `slide`'s text will not fit the slots it is written for."""
    title_problem = []
    if slots is not None and slots.title_chars is not None:
        if len(slide.title) > slots.title_chars * _LENGTH_SLACK:
            title_problem = [f"title is {len(slide.title)} chars (limit {slots.title_chars})"]
    return title_problem + _slot_length_problems(slide, slots)


def _slot_length_problems(slide: SlideContent, slots: SlotSummary | None) -> list[str]:
    if slots is not None and slots.kind == "cards" and slots.card_chars is not None:
        return [
            f"bullet {i} is {len(b)} chars (limit {slots.card_chars})"
            for i, b in enumerate(slide.bullets, start=1)
            if len(b) > slots.card_chars * _LENGTH_SLACK
        ]
    if slots is None or slots.kind != "body":
        return []
    limits = _body_limits(slots)
    if limits is None:
        return []
    max_bullets, per_item, body_total = limits
    problems = []
    if len(slide.bullets) > max_bullets:
        problems.append(f"{len(slide.bullets)} bullets, at most {max_bullets} fit")
    for i, bullet in enumerate(slide.bullets, start=1):
        if len(bullet) > per_item * _LENGTH_SLACK or len(bullet.split()) > _MAX_WORDS_PER_BULLET:
            problems.append(
                f"bullet {i} is {len(bullet)} chars / {len(bullet.split())} words "
                f"(limit {per_item} chars, {_MAX_WORDS_PER_BULLET} words)"
            )
    if slide.body and len(slide.body) > body_total * _LENGTH_SLACK:
        problems.append(f"body is {len(slide.body)} chars (limit {body_total})")
    return problems


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


# Models write notes somewhat short of any stated length — measured live at
# ~75% (the former nex models) to ~90% (the current free chain) of the
# target, even phrased as a floor. Asking for this much more lands the
# actual notes near the real speaking budget.
NOTES_UNDERSHOOT = 1.1


def _notes_line(seconds: int) -> str:
    spoken = seconds or DEFAULT_SLIDE_SECONDS
    words = round(words_for(spoken) * NOTES_UNDERSHOOT)
    return (
        f'"speaker_notes": {words} words, at least {round(words * 0.9)} (spoken over ~{spoken} s)'
    )


def _build_user_prompt(
    brief: str,
    outline: Outline,
    slot_summaries: list[SlotSummary | None],
    density: str | None = None,
    brand: str | None = None,
    only_slides: list[int] | None = None,
    text_mode: str | None = None,
    user_images: list[str] | None = None,
    speaker_notes: bool = True,
) -> str:
    """The content prompt for the whole deck, or for a group of its slides.

    With `only_slides` (0-based positions), the whole outline is still
    listed — so the writer knows what every other slide covers and doesn't
    repeat it — but only those slides get fill rules, and the reply holds
    exactly those slides, in order.
    """
    lines = [f"Brief:\n{brief}\n"]
    language = language_line(deck_language(brief))
    if language:
        lines.append(f"{language}\n")
    if text_mode in TEXT_MODE_LINES:
        lines.append(f"{TEXT_MODE_LINES[text_mode]}\n")
    if brand:
        lines.append(f"Brand guide (use its names and voice):\n{brand}\n")
    density_line = _DENSITY_LINES.get(density or "")
    if density_line:
        lines.append(f"{density_line}\n")
    if user_images:
        listed = "\n".join(f"  {n}. {name}" for n, name in enumerate(user_images, 1))
        lines.append(
            "The user's own images (number. file name):\n"
            f"{listed}\n"
            'On a slide whose "image_brief" is required, set "user_image" to the number '
            "of one of these that fits what the slide shows; each image on at most one "
            'slide; otherwise "user_image": null (a matching photo is then found online).\n'
        )
    if not speaker_notes:
        lines.append(
            'There is no talk — the deck is read, not presented: "speaker_notes": null '
            "on every slide.\n"
        )
    lines.append("Slides (in order):")
    for i, (slide, slots) in enumerate(zip(outline.slides, slot_summaries, strict=True)):
        entry = (
            f"{i + 1}. role: {slide.role}\n   intent: {slide.intent}\n   summary: {slide.summary}"
        )
        if only_slides is None or i in only_slides:
            entry += f"\n   {_slide_budget(slots)}"
            if speaker_notes:
                entry += f"\n   {_notes_line(slide.seconds)}"
        lines.append(entry)
    shape = (
        '{"role": ..., "title": ..., "bullets": [...], "body": ..., '
        '"table": [[...], ...], "image_brief": ..., "image_query": ..., '
        + ('"user_image": ..., ' if user_images else "")
        + ('"speaker_notes": ...}' if speaker_notes else '"speaker_notes": null}')
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
    deadline: float | None = None,
    text_mode: str | None = None,
    user_images: list[str] | None = None,
    speaker_notes: bool = True,
    client: InferenceClient | None = None,
) -> DeckContent:
    """Turn an outline into full per-slide content plus speaker notes.

    `deadline` (a `time.monotonic()` value) bounds the optional LLM repair
    passes: one is started only while there is still room for it to finish
    before the deadline. The deterministic fixes that follow always run, so
    a late draft is still grounded and sized — just repaired less gently.

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
        prompt = _build_user_prompt(
            brief,
            outline,
            slot_summaries,
            density,
            brand,
            only_slides,
            text_mode,
            user_images,
            speaker_notes,
        )
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

    language = deck_language(brief)

    def problems(content: DeckContent, numbers: list[int]) -> dict[int, list[str]]:
        found: dict[int, list[str]] = {}
        for n, bad in _ungrounded_by_slide(content, brief, [n + 1 for n in numbers]).items():
            for figure in sorted(bad):
                found.setdefault(n, []).append(
                    f"the figure {figure} is not in the brief — say it in words"
                )
        for n, slide in zip(numbers, content.slides, strict=False):
            for msg in _length_problems(slide, slot_summaries[n]):
                found.setdefault(n + 1, []).append(msg)
            # Unfilled slots would keep the template's own sample content.
            slots = slot_summaries[n]
            if slots is not None and slots.has_table and not slide.table:
                found.setdefault(n + 1, []).append(
                    'this slide has a table: fill "table" (header row + rows; '
                    "words, no invented figures)"
                )
            if slots is not None and slots.has_picture and not (slide.image_query or "").strip():
                found.setdefault(n + 1, []).append(
                    'this slide has a photo: give "image_query" (2-4 English keywords)'
                )
            # Language drift (see generator.language): the slide's visible
            # text and its notes must be in the deck's language.
            visible = " ".join([slide.title, *slide.bullets, slide.body or ""])
            if not is_in(language, visible) or not is_in(language, slide.speaker_notes or ""):
                found.setdefault(n + 1, []).append(f"write this slide entirely in {language}")
        return found

    def grounded(only_slides: list[int] | None, write) -> DeckContent:
        """Write, then corrective passes while the draft breaks a hard rule.

        The prompt's "never invent facts" and size rules are not reliable on
        their own; a pass naming the exact violations is. Slide numbers in the
        feedback are the deck's own (1-based), so they match the prompt's slide
        list in both whole-deck and group mode. A retry is kept only if it is
        no worse, and retrying stops as soon as one fails to improve. Whatever
        invented figures survive are then dropped deterministically.
        """
        content = write("")
        numbers = list(only_slides if only_slides is not None else range(len(content.slides)))
        found = problems(content, numbers)
        for _ in range(_MAX_CORRECTIONS):
            if not found or not _has_time(deadline):
                break
            feedback = "\n".join(f"- slide {i}: {'; '.join(m)}" for i, m in found.items())
            retry = write(
                "\n\nYour previous draft broke these rules:\n"
                f"{feedback}\nRewrite the same slides with the same structure and fix every "
                "point: no numbers, percentages or durations the brief does not itself state "
                "(argue in words), and text short enough for its area."
            )
            retry_found = problems(retry, numbers)
            if len(retry.slides) != len(content.slides) or sum(map(len, retry_found.values())) > (
                sum(map(len, found.values()))
            ):
                break
            improved = sum(map(len, retry_found.values())) < sum(map(len, found.values()))
            content, found = retry, retry_found
            if not improved:
                break
        slots = [slot_summaries[n] for n in numbers]
        content = _repair_strings(content, brief, slots, inference_client, deadline)
        return _fit_bullet_count(_drop_ungrounded(content, brief, slots), slots)

    if not parallel:
        content = grounded(None, lambda extra: call(None, extra))
        return _finish(content, slot_summaries, user_images, speaker_notes)

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
                except (QuotaExhausted, DeadlineExceeded):
                    raise  # retrying can't help
                except Exception as exc:
                    last_error = exc
            raise last_error or RuntimeError(f"slides {positions} failed")

        try:
            return grounded(positions, write).slides
        except QuotaExhausted:
            raise
        except Exception:
            if deadline is None:
                raise
            # Out of time (or the free pool failed us) for this group: its
            # slides come from the outline, so the deck still arrives in
            # budget — plainer, but complete and grounded.
            failed_groups.append(positions)
            return [_outline_slide(outline.slides[i]) for i in positions]

    count = len(outline.slides)
    size = max(1, -(-count // CONTENT_CALLS))
    groups = [list(range(start, min(start + size, count))) for start in range(0, count, size)]
    failed_groups: list[list[int]] = []
    with ThreadPoolExecutor(max_workers=max(1, len(groups))) as pool:
        written = list(pool.map(group, groups))
    if len(failed_groups) == len(groups):
        raise DeadlineExceeded("no slide group finished within the time budget")
    content = DeckContent(slides=[slide for chunk in written for slide in chunk])
    return _finish(content, slot_summaries, user_images, speaker_notes)


def _finish(
    content: DeckContent,
    slots: list[SlotSummary | None],
    user_images: list[str] | None,
    speaker_notes: bool,
) -> DeckContent:
    """Final clean-up: valid image picks; no notes at all when there is no talk."""
    if not speaker_notes:
        for slide in content.slides:
            slide.speaker_notes = None
    return _valid_user_images(content, slots, len(user_images or []))


def _valid_user_images(
    content: DeckContent, slots: list[SlotSummary | None], available: int
) -> DeckContent:
    """Keep only usable `user_image` picks: an existing image, on a slide with a
    photo frame, each image once (groups are written in parallel, so two may
    pick the same one — the earlier slide keeps it)."""
    used: set[int] = set()
    for slide, slot in zip(content.slides, slots, strict=False):
        pick = slide.user_image
        ok = (
            pick is not None
            and 1 <= pick <= available
            and pick not in used
            and (slot is None or slot.has_picture)
        )
        slide.user_image = pick if ok else None
        if ok:
            used.add(pick)
    return content


def _outline_slide(intent) -> SlideContent:
    """Minimal slide from its outline entry: the planned claim as title and note."""
    return SlideContent(
        role=intent.role, title=intent.summary, speaker_notes=intent.summary
    )


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


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _drop_ungrounded(
    content: DeckContent, brief: str, slots: list[SlotSummary | None]
) -> DeckContent:
    """Last resort once rewrites are exhausted: remove claims with invented figures.

    Bullets (on free-text slides — a card slide's bullet count is structural)
    and sentences of `body`/`speaker_notes` that state a figure the brief never
    does are dropped, always leaving at least one bullet. Better a shorter
    slide than a fabricated statistic on it.
    """
    allowed = figures(brief)

    def clean(text: str) -> str:
        kept = [x for x in _SENTENCE_SPLIT.split(text) if not figures(x) - allowed]
        return " ".join(kept)

    for slide, slot in zip(content.slides, slots, strict=False):
        if slot is None or slot.kind != "cards":
            kept = [b for b in slide.bullets if not figures(b) - allowed]
            if kept:
                slide.bullets = kept
        if slide.body and figures(slide.body) - allowed:
            slide.body = clean(slide.body) or slide.body
        if slide.speaker_notes and figures(slide.speaker_notes) - allowed:
            slide.speaker_notes = clean(slide.speaker_notes) or None
    return content


def _char_cap(slot: SlotSummary | None, field: str) -> int | None:
    """Character budget for one string of `field` on a slide with `slot`."""
    if slot is None:
        return None
    if field == "title":
        return slot.title_chars
    if slot.kind == "cards" and field == "bullet":
        return slot.card_chars
    if slot.kind == "body":
        limits = _body_limits(slot)
        if limits is None:
            return None
        if field == "bullet":
            return limits[1]
        if field == "body":
            return limits[2]
    return None


def _repair_strings(
    content: DeckContent,
    brief: str,
    slots: list[SlotSummary | None],
    client: InferenceClient,
    deadline: float | None = None,
) -> DeckContent:
    """Rewrite just the strings still breaking a rule, each with its own rule.

    Covers what whole-slide rewrites did not fix: an invented figure in a
    title, a card (whose count is structural, so it cannot simply be dropped)
    or a table cell, and a string too long for its slot. Each result is
    accepted only if it really is better, so a bad rewrite can never make a
    slide worse. A second round aims a little below the limit for strings the
    first round could not bring under it.
    """
    for tightness in (1.0, 0.75):
        if not _has_time(deadline) or not _repair_round(content, brief, slots, client, tightness):
            break
    return content


# Time one repair call may take on the free pool; a repair is only started
# with at least this much left before the deadline.
REPAIR_CALL_SECONDS = 60.0


def _has_time(deadline: float | None) -> bool:
    return deadline is None or time.monotonic() + REPAIR_CALL_SECONDS <= deadline


def _repair_round(
    content: DeckContent,
    brief: str,
    slots: list[SlotSummary | None],
    client: InferenceClient,
    tightness: float,
) -> bool:
    """One rewrite pass; True if any string changed."""
    allowed = figures(brief)
    targets: list[tuple[SlideContent, str, object, Fix]] = []
    for slide, slot in zip(content.slides, slots, strict=False):
        candidates: list[tuple[str, object, str]] = [("title", 0, slide.title)]
        candidates += [("bullet", i, b) for i, b in enumerate(slide.bullets)]
        candidates += [("body", 0, slide.body or ""), ("notes", 0, slide.speaker_notes or "")]
        for r, row in enumerate(slide.table or []):
            candidates += [("cell", (r, c), text) for c, text in enumerate(row)]
        for field, index, text in candidates:
            if not text:
                continue
            bad = sorted(figures(text) - allowed)
            cap = _char_cap(slot, field)
            too_long = cap is not None and len(text) > cap * _LENGTH_SLACK
            wordy = field == "bullet" and len(text.split()) > _MAX_WORDS_PER_BULLET
            if bad or too_long or wordy:
                limit = int(cap * tightness) if too_long and cap is not None else None
                words = _MAX_WORDS_PER_BULLET if wordy else None
                targets.append((slide, field, index, Fix(text, bad, limit, words)))
    if not targets:
        return False

    changed = False
    rewritten = rewrite_strings([t[3] for t in targets], client)
    for (slide, field, index, fix), new in zip(targets, rewritten, strict=True):
        if new == fix.text or figures(new) - allowed:
            continue
        if fix.max_chars is not None and len(new) > fix.max_chars * _LENGTH_SLACK:
            continue
        if fix.max_words is not None and len(new.split()) > fix.max_words:
            continue
        changed = True
        if field == "title":
            slide.title = new
        elif field == "bullet":
            slide.bullets[index] = new  # type: ignore[index]
        elif field == "body":
            slide.body = new
        elif field == "cell":
            r, c = index  # type: ignore[misc]
            assert slide.table is not None
            slide.table[r][c] = new
        else:
            slide.speaker_notes = new
    return changed


def _fit_bullet_count(content: DeckContent, slots: list[SlotSummary | None]) -> DeckContent:
    """Cut a free-text slide's bullets to what its text area can hold.

    Rewrites and prompts both ask for this; a writer that ignores them anyway
    must not push text past the box. Trailing bullets go first — the outline
    orders points by importance.
    """
    for slide, slot in zip(content.slides, slots, strict=False):
        if slot is None or slot.kind != "body":
            continue
        limits = _body_limits(slot)
        if limits is not None and len(slide.bullets) > limits[0]:
            slide.bullets = slide.bullets[: limits[0]]
    return content
