"""Content + template + patterns -> composed slide IR.

`compose_deck` is the whole of `packages/layout`'s v1 surface: no LLM call
here, pure Python composition (see ARCHITECTURE.md's `layout` section). For
each `SlideContent` it finds a real `Slide` in the parsed template `Deck`
whose `layout_name == SlideContent.role`, deep-copies that slide's shape
list as the structural base (real geometry/fonts/fills/z-order), and
overwrites only its text-bearing shapes' content in place. Shapes are never
synthesized from scratch — this is what keeps the output faithful to the
template (DESIGN_PHILOSOPHY.md: "шаблон — источник истины").

Shape-to-content matching uses `ShapeBase.placeholder_type` exclusively —
never `name` or position — so it generalizes to a template never seen
before (same discipline `design_system/patterns.py` already establishes for
this codebase).

Variant axis = content density (`PRODUCT.md`'s stated leading candidate):
`"compact"` / `"standard"` / `"detailed"`. See `_variant_text` for the exact
rule each one applies.
"""

from __future__ import annotations

import re
from typing import Literal

from design_system import (
    apply_factor,
    extract_typography,
    fit_factor,
    is_body_placeholder,
    is_non_content_shape,
    is_title,
    pick_template_slides,
    repeated_slot_groups,
    shape_has_text,
)
from generator.content import DeckContent, SlideContent
from ir_schema import (
    AutoShape,
    Deck,
    Paragraph,
    PassthroughShape,
    Picture,
    Shape,
    Slide,
    Table,
    TableCell,
    TextBoxShape,
    TextRun,
)

Variant = Literal["compact", "standard", "detailed"]

# AUDIT.md "Плотность": table shapes must stay within these bounds.
MAX_TABLE_ROWS = 7
MAX_TABLE_COLS = 5


def _shape_area(shape: Shape) -> int:
    return max(shape.width, 0) * max(shape.height, 0)


def _representative_run_style(shape: TextBoxShape | AutoShape) -> TextRun | None:
    """Sample style attributes from the shape's existing first run, if any.

    Per spec: reused so substituted text doesn't come out unstyled/default;
    if there's no existing run to sample, callers get `None` and leave style
    fields `None` so export/PowerPoint's own placeholder-level defaults apply.
    """
    for paragraph in shape.paragraphs:
        for run in paragraph.runs:
            return run
    return None


def _make_run(text: str, style: TextRun | None) -> TextRun:
    if style is None:
        return TextRun(text=text)
    return TextRun(
        text=text,
        font_name=style.font_name,
        font_size_pt=style.font_size_pt,
        bold=style.bold,
        italic=style.italic,
        underline=style.underline,
        color=style.color,
    )


def _make_paragraph(text: str, style: TextRun | None, level: int = 0) -> Paragraph:
    return Paragraph(runs=[_make_run(text, style)], level=level)


def _set_text_shape(shape: TextBoxShape | AutoShape, paragraphs: list[Paragraph]) -> None:
    shape.paragraphs = paragraphs


def _title_paragraphs(title: str, style: TextRun | None) -> list[Paragraph]:
    return [_make_paragraph(title, style)]


def _variant_bullets(bullets: list[str], variant: Variant) -> list[str]:
    """Bullet slice for the given density variant.

    compact: first 3 (already importance-ordered). standard: all, clamped
    to 6 defensively (content skill already targets <=6). detailed: all,
    uncapped.
    """
    if variant == "compact":
        return bullets[:3]
    if variant == "standard":
        return bullets[:6]
    return list(bullets)


def _body_paragraphs(
    bullets: list[str], body: str | None, variant: Variant, style: TextRun | None
) -> list[Paragraph]:
    """Body-placeholder paragraphs for one variant.

    Bullets become one paragraph per bullet (level 0 — no sub-bullet
    structure is generated upstream to preserve). `body`:
    - compact: dropped, even if present.
    - standard: only included if there's a *separate* dedicated body slot
      (see `_fill_body_shapes` below — when bullets and body share the one
      matched placeholder, standard skips `body` rather than concatenating
      it awkwardly onto the bullet list).
    - detailed: appended as a closing paragraph in the same placeholder,
      regardless of whether it has a dedicated slot.
    """
    bullet_slice = _variant_bullets(bullets, variant)
    paragraphs = [_make_paragraph(b, style) for b in bullet_slice]
    if variant == "detailed" and body:
        paragraphs.append(_make_paragraph(body, style))
    return paragraphs


def _fill_table(shape: Table, table: list[list[str]]) -> None:
    rows = table[:MAX_TABLE_ROWS]
    col_count = min(max((len(r) for r in rows), default=0), MAX_TABLE_COLS)
    new_rows: list[list[TableCell]] = []
    for row in rows:
        cells: list[TableCell] = []
        for i in range(col_count):
            text = row[i] if i < len(row) else ""
            cells.append(TableCell(paragraphs=[_make_paragraph(text, None)]))
        new_rows.append(cells)
    shape.rows = new_rows
    # Column/row geometry hints trimmed/padded to match, so export doesn't
    # index out of range against the new row/col counts.
    if shape.column_widths:
        if len(shape.column_widths) >= col_count:
            shape.column_widths = shape.column_widths[:col_count]
        else:
            last = shape.column_widths[-1] if shape.column_widths else 0
            shape.column_widths = shape.column_widths + [last] * (
                col_count - len(shape.column_widths)
            )
    if shape.row_heights:
        if len(shape.row_heights) >= len(new_rows):
            shape.row_heights = shape.row_heights[: len(new_rows)]
        else:
            last = shape.row_heights[-1] if shape.row_heights else 0
            shape.row_heights = shape.row_heights + [last] * (
                len(new_rows) - len(shape.row_heights)
            )


# Placeholder junk a real presentation template leaves in unfilled shapes:
# runs of X (latin or Cyrillic — "ХХХХХ", or a data-callout token like "ХХ%"
# — see design_system.slots.is_data_placeholder for the fuller story), lorem
# ipsum, TODO/placeholder markers. If a text shape still shows this after
# composition, we never gave it real content and it's template scaffolding,
# not design — blank it rather than leak it. 2+ (not 3+) catches the short
# "ХХ" data-placeholder convention too; a TITLE placeholder is always filled
# regardless of is_non_content_shape (titles have no "don't fill" option),
# so this is the safety net for a title/body slot whose sampled template
# text happened to be exactly one of these tokens.
_JUNK_RE = re.compile(r"[xXхХ]{2,}\s*%?|lorem ipsum|\btodo\b|placeholder", re.IGNORECASE)


def _looks_like_junk(shape: TextBoxShape | AutoShape) -> bool:
    text = " ".join(run.text for p in shape.paragraphs for run in p.runs)
    return bool(_JUNK_RE.search(text))


def _fill_slot_group(
    slots: list[TextBoxShape | AutoShape], content: SlideContent
) -> None:
    """One content item per slot, in reading order; clear any leftover slots.

    Density variants don't apply here — a 3-card template has 3 cards no
    matter the variant, so the template's slot count wins over the density
    axis. Bullets beyond the slot count are dropped (a content/template count
    mismatch; the content generator is given each pattern's shape counts
    upstream so it can aim for the right number, but nothing enforces it).
    """
    for i, shape in enumerate(slots):
        style = _representative_run_style(shape)
        text = content.bullets[i] if i < len(content.bullets) else ""
        _set_text_shape(shape, [_make_paragraph(text, style)] if text else [])


def _clear_unfilled_scaffolding(
    candidates: list[TextBoxShape | AutoShape],
    filled: list[TextBoxShape | AutoShape],
) -> None:
    """Blank leftover template prompt text in every fallback shape we didn't fill.

    `candidates` is every non-title, non-body-placeholder text shape on the
    slide; `filled` is whichever subset the card/body logic just wrote real
    content into. Anything left over still carries whatever the *template's
    own sample slide* had in it — repeated caption rows ("Текст" x3), but
    also one-off per-instance labels (seen live: a specific card-layout
    instance had a lone "Заметка"/"Кейс" pair with no size-twin on that same
    slide, so a repeated-group-only clear left them leaking). Since content
    generation never targets these shapes at all, "still has template text"
    and "is scaffolding we chose not to fill" are the same fact here — there
    is no real design element this pipeline intentionally leaves untouched
    among the fallback candidates, so blank unconditionally rather than only
    within detected repeated groups.
    """
    filled_ids = {id(s) for s in filled}
    for shape in candidates:
        if id(shape) not in filled_ids:
            _set_text_shape(shape, [])


def _fill_body_shapes(
    body_shapes: list[TextBoxShape | AutoShape],
    content: SlideContent,
    variant: Variant,
) -> None:
    """Distribute bullets/body across one or more matched body-ish shapes.

    One dedicated shape (the common case): bullets go there, and `body` (for
    "standard") is skipped per the rule above since there's no separate slot
    — "detailed" still appends it to the same placeholder. Two or more
    shapes: fill each with a distinct slice in placeholder document order
    rather than duplicating content — first shape gets the bullets, a
    second gets `body` as its own paragraph (this *is* body's dedicated
    slot, so "standard" includes it there).
    """
    if not body_shapes:
        return

    style = _representative_run_style(body_shapes[0])

    if len(body_shapes) == 1:
        _set_text_shape(
            body_shapes[0],
            _body_paragraphs(content.bullets, content.body, variant, style),
        )
        return

    bullet_slice = _variant_bullets(content.bullets, variant)
    _set_text_shape(body_shapes[0], [_make_paragraph(b, style) for b in bullet_slice])

    second_style = _representative_run_style(body_shapes[1])
    if variant == "compact":
        _set_text_shape(body_shapes[1], [])
    elif content.body:
        _set_text_shape(body_shapes[1], [_make_paragraph(content.body, second_style)])
    else:
        _set_text_shape(body_shapes[1], [])

    # Any further body-ish shapes beyond the first two are left untouched
    # (no more distinct content to distribute without duplicating).


def _compose_slide(template_slide: Slide, content: SlideContent, variant: Variant) -> Slide:
    slide = template_slide.model_copy(deep=True)

    title_shapes: list[TextBoxShape | AutoShape] = []
    placeholder_body_shapes: list[TextBoxShape | AutoShape] = []
    table_shapes: list[Table] = []
    fallback_candidates: list[TextBoxShape | AutoShape] = []

    for shape in slide.shapes:
        if isinstance(shape, (Picture, PassthroughShape)):
            continue
        if isinstance(shape, Table):
            table_shapes.append(shape)
            continue
        if not isinstance(shape, (TextBoxShape, AutoShape)):
            continue

        if is_title(shape):
            title_shapes.append(shape)
        elif is_body_placeholder(shape):
            placeholder_body_shapes.append(shape)
        elif not is_non_content_shape(shape):
            # A shape template-labeled "QR-code"/"Ссылка"/"Лого" (fixed UI
            # chrome) or styled as a display accent (a big stat number, a
            # giant "Q&A") is never a fill target — left untouched exactly
            # like a Picture (see design_system.slots for the live failures
            # this fixes: full bullet lists crammed into a QR box and a
            # 144pt "Q&A" heading).
            fallback_candidates.append(shape)

    # Title: fill every TITLE/CENTER_TITLE placeholder with the same title.
    for shape in title_shapes:
        style = _representative_run_style(shape)
        _set_text_shape(shape, _title_paragraphs(content.title, style))

    # Body placement, in priority order:
    #  1. Real BODY/SUBTITLE/OBJECT placeholders -> the classic title+body case.
    #  2. Else, a repeated slot group (a card grid / column row): distribute
    #     one content item per slot, and blank the other repeated scaffolding
    #     (captions etc.) so no template prompt text leaks.
    #  3. Else, the single largest text shape gets the whole body blob.
    if placeholder_body_shapes:
        _fill_body_shapes(placeholder_body_shapes, content, variant)
    elif fallback_candidates:
        slot_groups = repeated_slot_groups(fallback_candidates)
        if slot_groups:
            primary = slot_groups[0]
            _fill_slot_group(primary, content)
            _clear_unfilled_scaffolding(fallback_candidates, filled=primary)
        else:
            # Last resort: the single largest candidate gets the body blob —
            # but only among shapes that *originally carried template text*.
            # A shape empty in the template (a decorative rect, a background
            # bar) was never a content slot; picking it just because it's
            # the biggest empty box on the slide dumps text onto furniture
            # (confirmed live, one level below the QR-code case above: once
            # the QR/link shapes were excluded, an empty decorative rectangle
            # became "the largest candidate" and inherited the bullets meant
            # for a title-only slide). If nothing had text, there is no real
            # slot for a body blob — leave every fallback shape untouched.
            textful = [s for s in fallback_candidates if shape_has_text(s)]
            if textful:
                chosen = max(textful, key=_shape_area)
                _fill_body_shapes([chosen], content, variant)
                _clear_unfilled_scaffolding(fallback_candidates, filled=[chosen])

    # Table: only if content provides one; otherwise leave the template's
    # own table content untouched (don't invent data).
    if content.table is not None:
        for shape in table_shapes:
            _fill_table(shape, content.table)

    # Final pass: any text shape still showing template junk (XXXXX, lorem,
    # leftover sample copy we never overwrote) gets blanked — this catches the
    # *unique* leftover shapes that the repeated-scaffolding clear above can't.
    for shape in slide.shapes:
        if isinstance(shape, (TextBoxShape, AutoShape)) and _looks_like_junk(shape):
            _set_text_shape(shape, [])

    return slide


def _fit_text_to_boxes(slide: Slide, type_scale: list[float]) -> None:
    """Shrink text that would spill out of its box, on the template's own type scale.

    The exported .pptx carries no autofit, so text taller than its box would
    spill in PowerPoint even though the browser preview shrinks it to fit.
    Members of a repeated group (cards / columns) share the smallest factor any
    of them needs, so parallel slots never end up at mismatched sizes.
    """
    shapes = [
        s
        for s in slide.shapes
        if isinstance(s, (TextBoxShape, AutoShape)) and shape_has_text(s)
    ]
    groups: dict[tuple[str, int, int], list[TextBoxShape | AutoShape]] = {}
    for shape in shapes:
        groups.setdefault((shape.kind, shape.width, shape.height), []).append(shape)
    for members in groups.values():
        factor = min(fit_factor(m, type_scale) for m in members)
        for member in members:
            apply_factor(member, type_scale, factor)


def compose_deck(deck_content: DeckContent, template_deck: Deck, variant: Variant) -> Deck:
    """Compose a full deck for one density `variant` from generated content.

    For each `SlideContent` in `deck_content.slides`, finds a template
    `Slide` whose `layout_name == SlideContent.role` in `template_deck`
    (round-robins through same-role template slides so repeated roles don't
    all reuse instance 0), deep-copies its shapes, and overwrites
    text-bearing placeholders per the matching rules in this module's
    docstring. Raises `ValueError` if a role has no matching template slide.
    `template_deck` is never mutated.
    """
    # Same assignment content generation was written against (each slide's text
    # was sized for its exact template slide's slots) — see pick_template_slides.
    template_slides = pick_template_slides([c.role for c in deck_content.slides], template_deck)
    composed_slides = [
        _compose_slide(template_slide, content, variant)
        for template_slide, content in zip(template_slides, deck_content.slides, strict=True)
    ]
    type_scale = [t.size_pt for t in extract_typography(template_deck).type_scale]
    for slide in composed_slides:
        _fit_text_to_boxes(slide, type_scale)

    # `_compose_slide` deep-copies the matched template slide, which carries
    # that slide's own `index` from `template_deck` — e.g. a role matched to
    # template slide 9 keeps `.index == 9` even when it's the 3rd slide in
    # this generated deck. Downstream code (`packages/audit`'s findings,
    # eventual export ordering) needs `.index` to mean "position in *this*
    # deck", so it's reset here to match `composed_slides`' actual order.
    for position, (slide, content) in enumerate(
        zip(composed_slides, deck_content.slides, strict=True)
    ):
        slide.index = position
        slide.notes = content.speaker_notes

    return Deck(
        slide_width=template_deck.slide_width,
        slide_height=template_deck.slide_height,
        source_path=template_deck.source_path,
        theme_colors=template_deck.theme_colors,
        slides=composed_slides,
    )
