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
    Item,
    apply_factor,
    extract_typography,
    find_items,
    fit_factor,
    is_body_placeholder,
    is_display_accent,
    is_functional_chrome,
    is_non_content_shape,
    is_title,
    pick_template_slides,
    repeated_slot_groups,
    shape_has_text,
    title_on_plate,
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


# " — ", " – ", ": " split a two-field card item into heading and text.
_ITEM_SPLIT = re.compile(r"\s+[—–]\s+|:\s+")
_NUMBERING = re.compile(r"^\s*\d{1,2}[.)]?\s*$")


def _split_item(text: str) -> tuple[str, str]:
    parts = _ITEM_SPLIT.split(text, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return text.strip(), ""


def _fill_items(items: list[Item], content: SlideContent) -> None:
    """One content item per template item, in the set's reading order.

    Two-field items (a step's heading over its description, a stat's number
    over its caption) take "Heading — text" apart; the writer is asked for
    exactly that shape (see generator.content's card fill rule). Items beyond
    the content are blanked; content beyond the items is dropped.
    """
    for i, item in enumerate(items):
        text = content.bullets[i] if i < len(content.bullets) else ""
        if item.heading is not None:
            heading, body = _split_item(text) if text else ("", "")
            fields = [(item.heading, heading), (item.text, body)]
        else:
            fields = [(item.text, text)]
        for shape, value in fields:
            style = _representative_run_style(shape)
            _set_text_shape(shape, [_make_paragraph(value, style)] if value else [])


def _text_key(shape: TextBoxShape | AutoShape) -> str:
    return "\n".join("".join(r.text for r in p.runs) for p in shape.paragraphs).strip()


_NUMBER = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def _chart_table(table: list[list[str]] | None) -> list[list[str]] | None:
    """`table` if it can drive a chart: a header plus rows of category + numbers."""
    if not table or len(table) < 2 or len(table[0]) < 2:
        return None
    width = len(table[0])
    for row in table[1:]:
        if len(row) != width or not all(_NUMBER.search(cell) for cell in row[1:]):
            return None
    return table


def _fill_or_drop_charts(slide: Slide, table: list[list[str]] | None) -> None:
    """Give every template chart the writer's numbers, or remove it.

    A template chart ships with its designer's sample series ("2021-2024,
    Ряд 1"); shown as-is it presents invented data as the speaker's own. So
    a chart survives composition only carrying numbers the writer took from
    the brief (grounding already checks table cells); otherwise it goes.
    """
    data = _chart_table(table)
    kept: list[Shape] = []
    for shape in slide.shapes:
        if isinstance(shape, PassthroughShape) and shape.is_chart:
            if data is None:
                continue
            shape.chart_data = data
        kept.append(shape)
    slide.shapes = kept


def _clear_template_leftovers(slide: Slide, template_slide: Slide) -> None:
    """Blank every text shape still showing the template's own sample text.

    Whatever composition didn't write into still carries the template
    author's placeholder copy ("Имя Фамилия", "Роль в команде", a sample
    topic's tagline) — scaffolding for a different deck. Kept: the title,
    step numbering ("1".."5" is design), functional chrome (QR/link labels)
    and display accents, which the rest of the pipeline treats as design.
    """
    original = {
        s.shape_id: _text_key(s)
        for s in template_slide.shapes
        if isinstance(s, (TextBoxShape, AutoShape))
    }
    for shape in slide.shapes:
        if not isinstance(shape, (TextBoxShape, AutoShape)) or is_title(shape):
            continue
        text = _text_key(shape)
        if not text or text != original.get(shape.shape_id):
            continue
        if _NUMBERING.match(text) or is_functional_chrome(shape) or is_display_accent(shape):
            continue
        _set_text_shape(shape, [])


def _drop_unused_placeholders(slide: Slide) -> None:
    """Remove content placeholders left empty, so no prompt text shows.

    An empty body placeholder renders its layout prompt ("Образец текста")
    in editors and in some viewers' exports. Titles are always filled;
    picture/number/date placeholders are design and stay.
    """
    slide.shapes = [
        s
        for s in slide.shapes
        if not (
            isinstance(s, (TextBoxShape, AutoShape))
            and is_body_placeholder(s)
            and not is_title(s)
            and not shape_has_text(s)
        )
    ]


def _compose_slide(
    template_slide: Slide, content: SlideContent, variant: Variant, slide_area: int
) -> Slide:
    slide = template_slide.model_copy(deep=True)
    items = find_items(slide)

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
    #  0. A parallel item set (see design_system.items) -> one item per slot.
    #  1. Real BODY/SUBTITLE/OBJECT placeholders -> the classic title+body case.
    #  2. Else, a repeated slot group (a card grid / column row): distribute
    #     one content item per slot, and blank the other repeated scaffolding
    #     (captions etc.) so no template prompt text leaks.
    #  3. Else, the single largest text shape gets the whole body blob.
    if items:
        _fill_items(items, content)
    elif placeholder_body_shapes:
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

    _fill_or_drop_charts(slide, None if table_shapes else content.table)

    # Final pass: any text shape still showing template junk (XXXXX, lorem,
    # leftover sample copy we never overwrote) gets blanked — this catches the
    # *unique* leftover shapes that the repeated-scaffolding clear above can't.
    for shape in slide.shapes:
        if isinstance(shape, (TextBoxShape, AutoShape)) and _looks_like_junk(shape):
            _set_text_shape(shape, [])

    _clear_template_leftovers(slide, template_slide)
    _prune_emptied_callouts(slide, template_slide, slide_area)
    _drop_unused_placeholders(slide)
    return slide


_CALLOUT_MAX_AREA = 0.25
_CALLOUT_MAX_PARTS = 4


def _contains(outer: Shape, inner: Shape, tolerance: float = 0.9) -> bool:
    """True if at least `tolerance` of `inner`'s area lies inside `outer`."""
    left = max(outer.left, inner.left)
    top = max(outer.top, inner.top)
    right = min(outer.left + outer.width, inner.left + inner.width)
    bottom = min(outer.top + outer.height, inner.top + inner.height)
    overlap = max(0, right - left) * max(0, bottom - top)
    area = _shape_area(inner)
    return area > 0 and overlap / area >= tolerance


def _prune_emptied_callouts(slide: Slide, template_slide: Slide, slide_area: int) -> None:
    """Remove the decoration left behind when a callout's text was blanked.

    A template "note"/"case" callout is a filled box, a badge, an icon and a
    caption. When the content has nothing for it, blanking only the caption
    leaves an unexplained coloured box on the slide. So: for every text shape
    that had template text and is now empty, drop it together with the
    text-less shape behind it and whatever icons/badges sit inside that shape.
    Title and body shapes are never pruned.
    """
    originally_texted = {
        s.shape_id
        for s in template_slide.shapes
        if isinstance(s, (TextBoxShape, AutoShape)) and shape_has_text(s)
    }
    emptied = [
        s
        for s in slide.shapes
        if isinstance(s, (TextBoxShape, AutoShape))
        and s.shape_id in originally_texted
        and not shape_has_text(s)
        and not is_title(s)
        and not is_body_placeholder(s)
    ]
    if not emptied:
        return

    remove: set[int] = {s.shape_id for s in emptied if isinstance(s, AutoShape) and s.fill_color}
    for cleared in emptied:
        backdrops = [
            s
            for s in slide.shapes
            if isinstance(s, AutoShape)
            and not shape_has_text(s)
            and s.shape_id not in originally_texted
            and s.shape_id != cleared.shape_id
            and _contains(s, cleared)
            and _shape_area(s) < _CALLOUT_MAX_AREA * slide_area
        ]
        if not backdrops:
            continue
        backdrop = min(backdrops, key=_shape_area)
        # A plate that still holds filled text is a live card, not an orphan.
        if any(
            isinstance(o, (TextBoxShape, AutoShape))
            and shape_has_text(o)
            and _contains(backdrop, o)
            for o in slide.shapes
        ):
            continue
        inside = [
            other.shape_id
            for other in slide.shapes
            if other.shape_id not in (backdrop.shape_id, cleared.shape_id)
            and not (isinstance(other, (TextBoxShape, AutoShape)) and shape_has_text(other))
            and _contains(backdrop, other)
        ]
        # A callout is small: a box with a handful of icons. A big panel holding
        # many shapes is a layout structure, not something to strip.
        if len(inside) > _CALLOUT_MAX_PARTS:
            continue
        remove.update([backdrop.shape_id, cleared.shape_id, *inside])
    slide.shapes = [s for s in slide.shapes if s.shape_id not in remove]


# Average glyph width of a bold display face, in ems — Montserrat-like
# headings run wider than the 0.5em body estimate used for capacities, and
# a viewer without the brand font substitutes something wider still.
_TITLE_EM = 0.72
_DEFAULT_TITLE_PT = 24.0
# A plated title may widen its own box up to this share of the slide width.
_TITLE_MAX_SHARE = 0.6
_EMU_PER_PT = 12_700


def _grow_plate_to_title(
    slide: Slide, title: TextBoxShape | AutoShape, slide_width: int
) -> None:
    """Widen the plate behind a one-line title so the text stays on it.

    Only ever grows, and never past the title's own box: the plate is the
    template's pill/bar, and a longer title needs a longer pill, not text
    trailing off it onto the background.
    """
    plated = title_on_plate(slide, title)
    if plated is title:
        return
    x = title.left + int(0.1 * 914_400)
    y = title.top + title.height // 2
    plates = [
        s
        for s in slide.shapes
        if isinstance(s, AutoShape)
        and not shape_has_text(s)
        and s.left <= x <= s.left + s.width
        and s.top <= y <= s.top + s.height
    ]
    if not plates:
        return
    plate = min(plates, key=_shape_area)
    runs = [r for p in title.paragraphs for r in p.runs if r.text]
    if not runs:
        return
    # A size inherited from the master isn't in the IR; titles are rarely
    # smaller than this, and overestimating only makes the pill a bit longer.
    size = max(r.font_size_pt or _DEFAULT_TITLE_PT for r in runs)
    text = " ".join("".join(r.text for r in p.runs) for p in title.paragraphs)
    inset = max(title.left - plate.left, 0)
    line = int(len(text) * size * _TITLE_EM * _EMU_PER_PT)
    # A title box narrower than its one line would wrap onto a second line
    # the plate can't hold — widen the box first, within reason.
    if line > title.width:
        title.width = max(title.width, min(line, int(slide_width * _TITLE_MAX_SHARE) - title.left))
    needed = line + 2 * inset
    limit = title.left + title.width + inset - plate.left
    if needed > plate.width:
        plate.width = min(needed, limit)


def _fit_text_to_boxes(slide: Slide, type_scale: list[float], slide_width: int) -> None:
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
    # A title on a coloured plate must fit the plate, not its (wider) box —
    # text past the plate's end runs onto the background. Shrink first; if
    # the one-line title is still longer than the plate, grow the plate.
    for title in [s for s in shapes if is_title(s)]:
        apply_factor(title, type_scale, fit_factor(title_on_plate(slide, title), type_scale))
        _grow_plate_to_title(slide, title, slide_width)
    shapes = [s for s in shapes if not is_title(s)]
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
    source_indexes = [s.index for s in template_slides]
    composed_slides = [
        _compose_slide(
            template_slide, content, variant, template_deck.slide_width * template_deck.slide_height
        )
        for template_slide, content in zip(template_slides, deck_content.slides, strict=True)
    ]
    type_scale = [t.size_pt for t in extract_typography(template_deck).type_scale]
    for slide in composed_slides:
        _fit_text_to_boxes(slide, type_scale, template_deck.slide_width)

    # `_compose_slide` deep-copies the matched template slide, which carries
    # that slide's own `index` from `template_deck` — e.g. a role matched to
    # template slide 9 keeps `.index == 9` even when it's the 3rd slide in
    # this generated deck. Downstream code (`packages/audit`'s findings,
    # eventual export ordering) needs `.index` to mean "position in *this*
    # deck", so it's reset here to match `composed_slides`' actual order.
    for position, (slide, content, source) in enumerate(
        zip(composed_slides, deck_content.slides, source_indexes, strict=True)
    ):
        slide.index = position
        slide.source_index = source
        slide.notes = content.speaker_notes

    return Deck(
        slide_width=template_deck.slide_width,
        slide_height=template_deck.slide_height,
        source_path=template_deck.source_path,
        theme_colors=template_deck.theme_colors,
        slides=composed_slides,
    )
