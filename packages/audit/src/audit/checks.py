"""Deterministic checks over a composed `Deck` IR.

`run_checks(deck, template_deck)` is the whole of this module's public
surface (see AUDIT.md's "Детерминированные" section and ARCHITECTURE.md's
`audit` section for how this fits the pipeline). Every check here reads
straight off the IR — no LLM/VLM calls, no rendering. `template_deck` (the
original parsed deck, *not* the generated one) is only used to derive the
"allowed" palette/fonts/sizes via `design_system.extract_colors`/
`extract_typography` — the template defines what's compliant, the composed
deck is what's being checked against it.

Model-graded findings (`kind="model"`) aren't implemented yet — see
`packages/audit/README.md` for the list of checks deliberately deferred.
"""

from __future__ import annotations

from itertools import combinations
from typing import Literal

from design_system import extract_colors, extract_typography
from ir_schema import AutoShape, Deck, Shape, Slide, Table, TextBoxShape
from pydantic import BaseModel

# --- tunables (documented inline per check below) ---------------------------

# shapes_overlap: two shapes "overlap" (rather than deliberately, slightly
# touch — e.g. a text box sitting on a decorative background rect) when their
# intersection area exceeds this fraction of the *smaller* shape's own area.
OVERLAP_AREA_FRACTION = 0.05

# text_overflow: estimate a paragraph's required height as
# font_size_pt * LINE_HEIGHT_MULTIPLIER, converted pt -> EMU, one line per
# paragraph (the IR has no wrap-point data, so multi-line wrapping within a
# single paragraph can't be predicted — this is a heuristic, not exact
# PowerPoint text layout). A shape is flagged only when the estimate exceeds
# the shape's actual height by more than TEXT_OVERFLOW_SLACK, to avoid
# flagging shapes with reasonable internal margins.
LINE_HEIGHT_MULTIPLIER = 1.2
PT_TO_EMU = 12700
TEXT_OVERFLOW_SLACK = 1.15
# Fallback line height for a run with no explicit font_size_pt (inherits a
# placeholder/theme default we can't resolve here) — a conservative body-text
# guess so such runs don't spuriously trigger (or hide) overflow.
DEFAULT_FONT_SIZE_PT = 18.0

# font_not_in_template / size_not_in_scale / color_not_in_palette
FONT_SIZE_TOLERANCE_PT = 0.5

# density
MAX_BULLETS = 6
MAX_BULLET_WORDS = 15
MAX_TABLE_ROWS = 7
MAX_TABLE_COLS = 5
# slide_fill_ratio: sum of shape bbox areas / slide area. This is an
# approximation — overlapping shapes double-count their overlap region, and
# we don't compute a true union area (not worth the complexity for a density
# heuristic).
FILL_RATIO_MIN = 0.25
FILL_RATIO_MAX = 0.75

# placeholder_text_left
PLACEHOLDER_MARKERS = ("lorem ipsum", "xxx", "todo", "вставьте текст")

_TITLE_TYPES = {"TITLE", "CENTER_TITLE"}
_BODY_TYPES = {"BODY", "SUBTITLE", "OBJECT"}


class Finding(BaseModel):
    check: str
    kind: Literal["deterministic"] = "deterministic"
    slide_index: int
    shape_id: int | None = None
    message: str


# --- shared helpers -----------------------------------------------------


def _placeholder_kind(shape: Shape) -> str | None:
    if shape.placeholder_type is None:
        return None
    return shape.placeholder_type.split(" (", 1)[0]


def _shape_area(shape: Shape) -> int:
    return max(shape.width, 0) * max(shape.height, 0)


def _bbox_intersection_area(a: Shape, b: Shape) -> int:
    left = max(a.left, b.left)
    top = max(a.top, b.top)
    right = min(a.left + a.width, b.left + b.width)
    bottom = min(a.top + a.height, b.top + b.height)
    if right <= left or bottom <= top:
        return 0
    return (right - left) * (bottom - top)


def _paragraph_text(paragraph) -> str:
    return "".join(run.text for run in paragraph.runs)


def _text_shapes(slide: Slide) -> list[TextBoxShape | AutoShape]:
    return [s for s in slide.shapes if isinstance(s, (TextBoxShape, AutoShape))]


def _title_shapes(slide: Slide) -> list[TextBoxShape | AutoShape]:
    return [s for s in _text_shapes(slide) if _placeholder_kind(s) in _TITLE_TYPES]


def _body_ish_shapes(slide: Slide) -> list[TextBoxShape | AutoShape]:
    """Mirrors `packages/layout/src/layout/compose.py`'s shape-matching rule:

    prefer real BODY/SUBTITLE/OBJECT placeholders; fall back to the largest
    non-title text-bearing shape when none exist on this pattern. Independent
    re-verification (see AUDIT.md's "Плотность"), so this is intentionally a
    parallel implementation rather than an import of layout's internals.
    """
    text_shapes = _text_shapes(slide)
    body = [s for s in text_shapes if _placeholder_kind(s) in _BODY_TYPES]
    if body:
        return body
    fallback = [s for s in text_shapes if _placeholder_kind(s) not in _TITLE_TYPES]
    if not fallback:
        return []
    return [max(fallback, key=_shape_area)]


def _contains_placeholder_marker(text: str) -> str | None:
    lowered = text.lower()
    for marker in PLACEHOLDER_MARKERS:
        if marker in lowered:
            return marker
    return None


# --- individual checks ----------------------------------------------------


def _check_shape_out_of_bounds(deck: Deck) -> list[Finding]:
    findings = []
    for slide in deck.slides:
        for shape in slide.shapes:
            out = (
                shape.left < 0
                or shape.top < 0
                or shape.left + shape.width > deck.slide_width
                or shape.top + shape.height > deck.slide_height
            )
            if out:
                findings.append(
                    Finding(
                        check="shape_out_of_bounds",
                        slide_index=slide.index,
                        shape_id=shape.shape_id,
                        message=(
                            f"shape {shape.shape_id!r} bbox "
                            f"(left={shape.left}, top={shape.top}, width={shape.width}, "
                            f"height={shape.height}) extends outside slide bounds "
                            f"(0, 0, {deck.slide_width}, {deck.slide_height})"
                        ),
                    )
                )
    return findings


def _check_shapes_overlap(deck: Deck) -> list[Finding]:
    findings = []
    for slide in deck.slides:
        for a, b in combinations(slide.shapes, 2):
            area_a, area_b = _shape_area(a), _shape_area(b)
            if area_a == 0 or area_b == 0:
                continue
            inter = _bbox_intersection_area(a, b)
            if inter == 0:
                continue
            smaller = min(area_a, area_b)
            if inter / smaller > OVERLAP_AREA_FRACTION:
                findings.append(
                    Finding(
                        check="shapes_overlap",
                        slide_index=slide.index,
                        shape_id=a.shape_id,
                        message=(
                            f"shape {a.shape_id!r} overlaps shape {b.shape_id!r}: "
                            f"intersection area {inter} EMU^2 is "
                            f"{inter / smaller:.0%} of the smaller shape's area "
                            f"(threshold {OVERLAP_AREA_FRACTION:.0%})"
                        ),
                    )
                )
    return findings


def _check_text_overflow(deck: Deck) -> list[Finding]:
    findings = []
    for slide in deck.slides:
        for shape in _text_shapes(slide):
            if not shape.paragraphs:
                continue
            estimated = 0.0
            for paragraph in shape.paragraphs:
                sizes = [r.font_size_pt for r in paragraph.runs if r.font_size_pt is not None]
                size = max(sizes) if sizes else DEFAULT_FONT_SIZE_PT
                estimated += size * LINE_HEIGHT_MULTIPLIER * PT_TO_EMU
            if shape.height > 0 and estimated > shape.height * TEXT_OVERFLOW_SLACK:
                findings.append(
                    Finding(
                        check="text_overflow",
                        slide_index=slide.index,
                        shape_id=shape.shape_id,
                        message=(
                            f"shape {shape.shape_id!r} estimated text height "
                            f"{estimated:.0f} EMU exceeds actual height {shape.height} EMU "
                            f"(heuristic: {LINE_HEIGHT_MULTIPLIER}x font size per paragraph "
                            "line, not exact PowerPoint layout)"
                        ),
                    )
                )
    return findings


def _check_template_compliance(deck: Deck, template_deck: Deck) -> list[Finding]:
    typography = extract_typography(template_deck)
    template_fonts = {f.name for f in typography.fonts}
    template_sizes = [s.size_pt for s in typography.type_scale]
    template_colors_rgb = {c.value for c in extract_colors(template_deck) if c.kind == "rgb"}

    def size_allowed(size: float) -> bool:
        return any(abs(size - allowed) <= FONT_SIZE_TOLERANCE_PT for allowed in template_sizes)

    findings = []
    for slide in deck.slides:
        for shape in slide.shapes:
            paragraph_lists = []
            if isinstance(shape, (TextBoxShape, AutoShape)):
                paragraph_lists.append(shape.paragraphs)
            if isinstance(shape, Table):
                for row in shape.rows:
                    for cell in row:
                        paragraph_lists.append(cell.paragraphs)

            for paragraphs in paragraph_lists:
                for paragraph in paragraphs:
                    for run in paragraph.runs:
                        if run.font_name is not None and run.font_name not in template_fonts:
                            findings.append(
                                Finding(
                                    check="font_not_in_template",
                                    slide_index=slide.index,
                                    shape_id=shape.shape_id,
                                    message=(
                                        f"run font {run.font_name!r} on shape "
                                        f"{shape.shape_id!r} is not in the template's font "
                                        f"vocabulary {sorted(template_fonts)}"
                                    ),
                                )
                            )
                        if run.font_size_pt is not None and not size_allowed(run.font_size_pt):
                            findings.append(
                                Finding(
                                    check="size_not_in_scale",
                                    slide_index=slide.index,
                                    shape_id=shape.shape_id,
                                    message=(
                                        f"run font size {run.font_size_pt}pt on shape "
                                        f"{shape.shape_id!r} is not in the template's type "
                                        f"scale {template_sizes} (tolerance "
                                        f"{FONT_SIZE_TOLERANCE_PT}pt)"
                                    ),
                                )
                            )
                        if (
                            run.color is not None
                            and run.color.kind == "rgb"
                            and run.color.rgb is not None
                            and run.color.rgb not in template_colors_rgb
                        ):
                            findings.append(
                                Finding(
                                    check="color_not_in_palette",
                                    slide_index=slide.index,
                                    shape_id=shape.shape_id,
                                    message=(
                                        f"run color {run.color.rgb!r} on shape "
                                        f"{shape.shape_id!r} is not in the template's palette "
                                        f"{sorted(template_colors_rgb)}"
                                    ),
                                )
                            )

            if (
                isinstance(shape, AutoShape)
                and shape.fill_color is not None
                and shape.fill_color.kind == "rgb"
                and shape.fill_color.rgb is not None
                and shape.fill_color.rgb not in template_colors_rgb
            ):
                findings.append(
                    Finding(
                        check="color_not_in_palette",
                        slide_index=slide.index,
                        shape_id=shape.shape_id,
                        message=(
                            f"fill color {shape.fill_color.rgb!r} on shape "
                            f"{shape.shape_id!r} is not in the template's palette "
                            f"{sorted(template_colors_rgb)}"
                        ),
                    )
                )
    return findings


def _check_too_many_bullets(deck: Deck) -> list[Finding]:
    findings = []
    for slide in deck.slides:
        body_shapes = _body_ish_shapes(slide)
        count = sum(
            1
            for shape in body_shapes
            for paragraph in shape.paragraphs
            if _paragraph_text(paragraph).strip()
        )
        if count > MAX_BULLETS:
            findings.append(
                Finding(
                    check="too_many_bullets",
                    slide_index=slide.index,
                    shape_id=None,
                    message=(
                        f"slide has {count} non-empty body paragraphs, exceeding the "
                        f"{MAX_BULLETS}-bullet density limit"
                    ),
                )
            )
    return findings


def _check_bullet_too_long(deck: Deck) -> list[Finding]:
    findings = []
    for slide in deck.slides:
        for shape in _text_shapes(slide):
            for paragraph in shape.paragraphs:
                text = _paragraph_text(paragraph).strip()
                if not text:
                    continue
                word_count = len(text.split())
                if word_count > MAX_BULLET_WORDS:
                    findings.append(
                        Finding(
                            check="bullet_too_long",
                            slide_index=slide.index,
                            shape_id=shape.shape_id,
                            message=(
                                f"paragraph on shape {shape.shape_id!r} has {word_count} "
                                f"words (limit {MAX_BULLET_WORDS}): {text!r}"
                            ),
                        )
                    )
    return findings


def _check_table_too_large(deck: Deck) -> list[Finding]:
    findings = []
    for slide in deck.slides:
        for shape in slide.shapes:
            if not isinstance(shape, Table):
                continue
            rows = len(shape.rows)
            cols = max((len(r) for r in shape.rows), default=0)
            if rows > MAX_TABLE_ROWS or cols > MAX_TABLE_COLS:
                findings.append(
                    Finding(
                        check="table_too_large",
                        slide_index=slide.index,
                        shape_id=shape.shape_id,
                        message=(
                            f"table {shape.shape_id!r} is {rows} rows x {cols} cols, "
                            f"exceeding the {MAX_TABLE_ROWS}x{MAX_TABLE_COLS} density limit"
                        ),
                    )
                )
    return findings


def _check_slide_fill_ratio(deck: Deck) -> list[Finding]:
    findings = []
    slide_area = deck.slide_width * deck.slide_height
    if slide_area <= 0:
        return findings
    for slide in deck.slides:
        total = sum(_shape_area(s) for s in slide.shapes)
        ratio = total / slide_area
        if ratio < FILL_RATIO_MIN or ratio > FILL_RATIO_MAX:
            findings.append(
                Finding(
                    check="slide_fill_ratio",
                    slide_index=slide.index,
                    shape_id=None,
                    message=(
                        f"slide shape-area fill ratio is {ratio:.0%} "
                        f"(approximation, overlaps double-count), outside the "
                        f"{FILL_RATIO_MIN:.0%}-{FILL_RATIO_MAX:.0%} target range"
                    ),
                )
            )
    return findings


def _check_placeholder_text_left(deck: Deck) -> list[Finding]:
    findings = []
    for slide in deck.slides:
        for shape in slide.shapes:
            paragraph_lists = []
            if isinstance(shape, (TextBoxShape, AutoShape)):
                paragraph_lists.append(shape.paragraphs)
            if isinstance(shape, Table):
                for row in shape.rows:
                    for cell in row:
                        paragraph_lists.append(cell.paragraphs)
            for paragraphs in paragraph_lists:
                for paragraph in paragraphs:
                    for run in paragraph.runs:
                        marker = _contains_placeholder_marker(run.text)
                        if marker:
                            findings.append(
                                Finding(
                                    check="placeholder_text_left",
                                    slide_index=slide.index,
                                    shape_id=shape.shape_id,
                                    message=(
                                        f"run text on shape {shape.shape_id!r} contains "
                                        f"placeholder marker {marker!r}: {run.text!r}"
                                    ),
                                )
                            )
    return findings


def _check_empty_or_title_only_slide(deck: Deck) -> list[Finding]:
    findings = []
    for slide in deck.slides:
        title_shape_ids = {s.shape_id for s in _title_shapes(slide)}
        has_non_title_text = False
        for shape in slide.shapes:
            if shape.shape_id in title_shape_ids:
                continue
            paragraph_lists = []
            if isinstance(shape, (TextBoxShape, AutoShape)):
                paragraph_lists.append(shape.paragraphs)
            if isinstance(shape, Table):
                for row in shape.rows:
                    for cell in row:
                        paragraph_lists.append(cell.paragraphs)
            for paragraphs in paragraph_lists:
                for paragraph in paragraphs:
                    if _paragraph_text(paragraph).strip():
                        has_non_title_text = True
        if not has_non_title_text:
            findings.append(
                Finding(
                    check="empty_or_title_only_slide",
                    slide_index=slide.index,
                    shape_id=None,
                    message="slide has no non-title shape with any non-whitespace text",
                )
            )
    return findings


def _slide_signature(slide: Slide) -> tuple[str, frozenset[str]]:
    title_shape_ids = {s.shape_id for s in _title_shapes(slide)}
    title_text = "".join(
        _paragraph_text(p) for s in _title_shapes(slide) for p in s.paragraphs
    ).strip()
    body_texts = set()
    for shape in _text_shapes(slide):
        if shape.shape_id in title_shape_ids:
            continue
        for paragraph in shape.paragraphs:
            text = _paragraph_text(paragraph).strip()
            if text:
                body_texts.add(text)
    return title_text, frozenset(body_texts)


def _check_duplicate_slide(deck: Deck) -> list[Finding]:
    findings = []
    seen: dict[tuple[str, frozenset[str]], int] = {}
    for slide in deck.slides:
        signature = _slide_signature(slide)
        first_index = seen.get(signature)
        if first_index is not None:
            findings.append(
                Finding(
                    check="duplicate_slide",
                    slide_index=slide.index,
                    shape_id=None,
                    message=(
                        f"slide {slide.index} duplicates slide {first_index} "
                        "(identical title and body/bullet text)"
                    ),
                )
            )
        else:
            seen[signature] = slide.index
    return findings


def run_checks(deck: Deck, template_deck: Deck) -> list[Finding]:
    """Run every deterministic check against `deck`, using `template_deck` to
    derive the allowed palette/fonts/sizes for template-compliance checks.
    """
    findings: list[Finding] = []
    findings += _check_shape_out_of_bounds(deck)
    findings += _check_shapes_overlap(deck)
    findings += _check_text_overflow(deck)
    findings += _check_template_compliance(deck, template_deck)
    findings += _check_too_many_bullets(deck)
    findings += _check_bullet_too_long(deck)
    findings += _check_table_too_large(deck)
    findings += _check_slide_fill_ratio(deck)
    findings += _check_placeholder_text_left(deck)
    findings += _check_empty_or_title_only_slide(deck)
    findings += _check_duplicate_slide(deck)
    return findings
