"""Apply the audit's findings the user chose to fix.

Each fix is a small, predictable edit of the deck's IR — shrink to fit, snap to
the template's own size/colour/font, move, clamp, cut — so a fix never asks a
model unless rewording is the only honest repair (an over-long bullet). Fixes
that would need judgement (a slide's meaning, a chart's data) are reported back
as skipped, with the reason, instead of guessed.

`apply_fixes` works on a copy; the caller's deck is never touched.
"""

from __future__ import annotations

import base64
import io
from collections.abc import Callable
from dataclasses import dataclass, field

from design_system import extract_colors, extract_typography, figures, strip_unsupported
from design_system.textfit import apply_factor, fit_factor
from generator.textfix import Fix, rewrite_strings
from inference import InferenceClient
from ir_schema import AutoShape, Color, Deck, Picture, Shape, Slide, Table, TextBoxShape
from PIL import Image
from pydantic import BaseModel

from audit import design_rules
from audit.checks import (
    MAX_BULLET_WORDS,
    MAX_BULLETS,
    MAX_TABLE_COLS,
    MAX_TABLE_ROWS,
    PLACEHOLDER_MARKERS,
    _body_ish_shapes,
    _paragraph_text,
    _text_extent,
)
from audit.finding import Finding

# Space kept between two text blocks after one is moved clear of the other.
GAP_EMU = 90_000


class Skipped(BaseModel):
    finding: Finding
    reason: str


class FixReport(BaseModel):
    deck: Deck
    applied: list[Finding] = []
    skipped: list[Skipped] = []


@dataclass
class _Context:
    deck: Deck
    template: Deck
    brief: str
    client: InferenceClient | None
    sizes: list[float] = field(default_factory=list)
    palette: list[str] = field(default_factory=list)
    main_font: str | None = None
    doomed: set[int] = field(default_factory=set)  # slide indexes to delete at the end

    def slide(self, index: int) -> Slide | None:
        return next((s for s in self.deck.slides if s.index == index), None)

    def shape(self, finding: Finding) -> Shape | None:
        slide = self.slide(finding.slide_index)
        if slide is None or finding.shape_id is None:
            return None
        return next((s for s in slide.shapes if s.shape_id == finding.shape_id), None)


class _CannotFix(Exception):
    """Raised by a fixer to say why the finding stays."""


# --- helpers ----------------------------------------------------------------


def _runs(shape: Shape):
    if isinstance(shape, (TextBoxShape, AutoShape)):
        return [r for p in shape.paragraphs for r in p.runs]
    if isinstance(shape, Table):
        return [r for row in shape.rows for c in row for p in c.paragraphs for r in p.runs]
    return []


def _nearest(value: float, options: list[float]) -> float:
    return min(options, key=lambda o: abs(o - value))


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _nearest_color(hex_color: str, palette: list[str]) -> str:
    r, g, b = _rgb(hex_color)
    return min(
        palette,
        key=lambda p: sum((a - c) ** 2 for a, c in zip((r, g, b), _rgb(p), strict=True)),
    )


# --- fixers: (context, finding) -> None, or raise _CannotFix -----------------


def _fix_text_overflow(ctx: _Context, f: Finding) -> None:
    shape = ctx.shape(f)
    if not isinstance(shape, (TextBoxShape, AutoShape)):
        raise _CannotFix("фигура не найдена")
    factor = fit_factor(shape, ctx.sizes)
    if factor >= 1.0:
        raise _CannotFix("по оценке текст уже помещается")
    apply_factor(shape, ctx.sizes, factor)


def _fix_size(ctx: _Context, f: Finding) -> None:
    shape = ctx.shape(f)
    if shape is None or not ctx.sizes:
        raise _CannotFix("не найдена фигура или шкала размеров шаблона")
    for run in _runs(shape):
        if run.font_size_pt is not None:
            run.font_size_pt = _nearest(run.font_size_pt, ctx.sizes)


def _fix_font(ctx: _Context, f: Finding) -> None:
    shape = ctx.shape(f)
    if shape is None or ctx.main_font is None:
        raise _CannotFix("не найдена фигура или шрифт шаблона")
    for run in _runs(shape):
        run.font_name = ctx.main_font


def _fix_color(ctx: _Context, f: Finding) -> None:
    shape = ctx.shape(f)
    if shape is None or not ctx.palette:
        raise _CannotFix("не найдена фигура или палитра шаблона")
    for run in _runs(shape):
        if run.color is not None and run.color.kind == "rgb" and run.color.rgb not in ctx.palette:
            run.color = Color(kind="rgb", rgb=_nearest_color(run.color.rgb, ctx.palette))
    if isinstance(shape, AutoShape) and shape.fill_color and shape.fill_color.kind == "rgb":
        if shape.fill_color.rgb not in ctx.palette:
            shape.fill_color = Color(
                kind="rgb", rgb=_nearest_color(shape.fill_color.rgb, ctx.palette)
            )


def _fix_bounds(ctx: _Context, f: Finding) -> None:
    shape = ctx.shape(f)
    if shape is None:
        raise _CannotFix("фигура не найдена")
    w, h = ctx.deck.slide_width, ctx.deck.slide_height
    shape.width = min(shape.width, w)
    shape.height = min(shape.height, h)
    shape.left = max(0, min(shape.left, w - shape.width))
    shape.top = max(0, min(shape.top, h - shape.height))


def _fix_overlap(ctx: _Context, f: Finding) -> None:
    slide, first = ctx.slide(f.slide_index), ctx.shape(f)
    second = None
    if slide is not None and f.related_shape_id is not None:
        second = next((s for s in slide.shapes if s.shape_id == f.related_shape_id), None)
    texts = (TextBoxShape, AutoShape)
    if not (isinstance(first, texts) and isinstance(second, texts)):
        raise _CannotFix("фигуры не найдены")
    upper, lower = sorted((first, second), key=lambda s: s.top)
    new_top = _text_extent(upper)[3] + GAP_EMU
    if new_top + lower.height > ctx.deck.slide_height:
        raise _CannotFix("ниже нет места, чтобы сдвинуть нижний блок")
    lower.top = new_top


def _fix_margin_or_guide(ctx: _Context, f: Finding) -> None:
    shape = ctx.shape(f)
    if shape is None:
        raise _CannotFix("фигура не найдена")
    guides = sorted({s.left for sl in ctx.template.slides for s in sl.shapes if s.width})
    if f.check == "misaligned" and guides:
        shape.left = int(_nearest(shape.left, [float(g) for g in guides]))
    margin = int(design_rules.MIN_MARGIN_FRACTION * ctx.deck.slide_width)
    shape.left = max(margin, min(shape.left, ctx.deck.slide_width - shape.width - margin))
    shape.top = max(margin, min(shape.top, ctx.deck.slide_height - shape.height - margin))


def _fix_contrast(ctx: _Context, f: Finding) -> None:
    slide, shape = ctx.slide(f.slide_index), ctx.shape(f)
    if slide is None or not isinstance(shape, (TextBoxShape, AutoShape)):
        raise _CannotFix("фигура не найдена")
    backdrop = design_rules._backdrop(shape, slide, ctx.deck)
    if backdrop is None:
        raise _CannotFix("цвет фона под текстом неизвестен")
    options = ctx.palette + ["000000", "FFFFFF"]
    best = max(options, key=lambda c: design_rules.contrast_ratio(c, backdrop))
    for run in _runs(shape):
        run.color = Color(kind="rgb", rgb=best)


def _fix_bullets_count(ctx: _Context, f: Finding) -> None:
    slide = ctx.slide(f.slide_index)
    if slide is None:
        raise _CannotFix("слайд не найден")
    for shape in _body_ish_shapes(slide):  # the limit is per text block
        kept, keep = 0, []
        for paragraph in shape.paragraphs:
            if not _paragraph_text(paragraph).strip():
                keep.append(paragraph)
            elif kept < MAX_BULLETS:
                keep.append(paragraph)
                kept += 1
        shape.paragraphs = keep


def _fix_bullet_length(ctx: _Context, f: Finding) -> None:
    shape = ctx.shape(f)
    if not isinstance(shape, (TextBoxShape, AutoShape)):
        raise _CannotFix("фигура не найдена")
    long = [p for p in shape.paragraphs if len(_paragraph_text(p).split()) > MAX_BULLET_WORDS]
    if not long:
        raise _CannotFix("ни один пункт не превышает лимит")
    texts = [_paragraph_text(p).strip() for p in long]
    if ctx.client is not None:
        new = rewrite_strings([Fix(t, max_words=MAX_BULLET_WORDS) for t in texts], ctx.client)
    else:
        new = texts
    for paragraph, old, text in zip(long, texts, new, strict=True):
        if len(text.split()) > MAX_BULLET_WORDS or text == old:  # the model did not shorten it
            text = " ".join(old.split()[:MAX_BULLET_WORDS]).rstrip(",;:—- ") + "…"
        paragraph.runs[0].text = text
        paragraph.runs = paragraph.runs[:1]


def _fix_table(ctx: _Context, f: Finding) -> None:
    shape = ctx.shape(f)
    if not isinstance(shape, Table):
        raise _CannotFix("таблица не найдена")
    shape.rows = [row[:MAX_TABLE_COLS] for row in shape.rows[:MAX_TABLE_ROWS]]
    shape.column_widths = shape.column_widths[:MAX_TABLE_COLS]
    shape.row_heights = shape.row_heights[:MAX_TABLE_ROWS]


def _fix_placeholder(ctx: _Context, f: Finding) -> None:
    shape = ctx.shape(f)
    if shape is None:
        raise _CannotFix("фигура не найдена")
    for run in _runs(shape):
        if any(m in run.text.lower() for m in PLACEHOLDER_MARKERS):
            run.text = ""


def _fix_figures(ctx: _Context, f: Finding) -> None:
    shape = ctx.shape(f)
    if shape is None:
        raise _CannotFix("фигура не найдена")
    allowed = figures(ctx.brief)
    for run in _runs(shape):
        if figures(run.text) - allowed:
            run.text = strip_unsupported(run.text, allowed)


def _fix_remove_slide(ctx: _Context, f: Finding) -> None:
    ctx.doomed.add(f.slide_index)


def _fix_brand_element(ctx: _Context, f: Finding) -> None:
    slide, shape = ctx.slide(f.slide_index), ctx.shape(f)
    source = next((t for t in ctx.template.slides if slide and t.index == slide.source_index), None)
    original = next(
        (s for s in (source.shapes if source else []) if s.shape_id == f.shape_id), None
    )
    if shape is None or original is None:
        raise _CannotFix("исходное положение в шаблоне неизвестно")
    shape.left, shape.top = original.left, original.top


def _fix_image_aspect(ctx: _Context, f: Finding) -> None:
    shape = ctx.shape(f)
    if not isinstance(shape, Picture) or not shape.image_bytes_b64 or shape.height <= 0:
        raise _CannotFix("картинка не найдена")
    with Image.open(io.BytesIO(base64.b64decode(shape.image_bytes_b64))) as image:
        px_w, px_h = image.size
    target = shape.width / shape.height
    natural = px_w / px_h
    shape.crop_left = shape.crop_right = shape.crop_top = shape.crop_bottom = 0.0
    if natural > target:  # too wide: trim the sides equally
        shape.crop_left = shape.crop_right = (1 - target / natural) / 2
    else:  # too tall: trim top and bottom equally
        shape.crop_top = shape.crop_bottom = (1 - natural / target) / 2


def _fix_fonts_all(ctx: _Context, f: Finding) -> None:
    if ctx.main_font is None:
        raise _CannotFix("шрифт шаблона не найден")
    for slide in ctx.deck.slides:
        for shape in slide.shapes:
            for run in _runs(shape):
                run.font_name = ctx.main_font


_FIXERS: dict[str, Callable[[_Context, Finding], None]] = {
    "text_overflow": _fix_text_overflow,
    "size_not_in_scale": _fix_size,
    "font_not_in_template": _fix_font,
    "too_many_font_families": _fix_fonts_all,
    "color_not_in_palette": _fix_color,
    "shape_out_of_bounds": _fix_bounds,
    "shapes_overlap": _fix_overlap,
    "margin_violation": _fix_margin_or_guide,
    "misaligned": _fix_margin_or_guide,
    "low_contrast": _fix_contrast,
    "too_many_bullets": _fix_bullets_count,
    "bullet_too_long": _fix_bullet_length,
    "table_too_large": _fix_table,
    "placeholder_text_left": _fix_placeholder,
    "unsupported_figure": _fix_figures,
    "empty_or_title_only_slide": _fix_remove_slide,
    "duplicate_slide": _fix_remove_slide,
    "brand_element_moved": _fix_brand_element,
    "image_distorted": _fix_image_aspect,
}

# Why the rest can't be fixed by a rule. Shown next to the finding.
NOT_AUTOMATIC = {
    "slide_fill_ratio": "баланс — решение дизайнера: сгенерируйте заново или поправьте вручную",
    "slide_is_picture": "вернуть нечего, текста нет: сгенерируйте слайд заново",
    "layout_not_from_template": "сгенерируйте слайд заново на макете из шаблона",
    "language_drift": "сгенерируйте текст заново на языке брифа",
    "chart_too_many_series": "какие ряды убрать — решает автор",
    "chart_missing_labels": "для подписей осей нужны единицы автора",
    "file_not_openable": "сам файл повреждён: экспортируйте заново",
}


def fixable(check: str) -> bool:
    """Whether `check`'s findings can be repaired by `apply_fixes` (shown in the UI)."""
    return check in _FIXERS


def apply_fixes(
    deck: Deck,
    template_deck: Deck,
    findings: list[Finding],
    brief: str = "",
    client: InferenceClient | None = None,
) -> FixReport:
    """A copy of `deck` with the chosen `findings` repaired, and a report of what happened."""
    typography = extract_typography(template_deck)
    ctx = _Context(
        deck=deck.model_copy(deep=True),
        template=template_deck,
        brief=brief,
        client=client,
        sizes=[t.size_pt for t in typography.type_scale],
        palette=[c.value for c in extract_colors(template_deck) if c.kind == "rgb"],
        main_font=typography.fonts[0].name if typography.fonts else None,
    )
    report = FixReport(deck=ctx.deck)
    # A font swap or size snap can change text height, so shrink-to-fit goes last.
    ordered = sorted(findings, key=lambda f: f.check == "text_overflow")
    for finding in ordered:
        fixer = _FIXERS.get(finding.check)
        if fixer is None:
            reason = NOT_AUTOMATIC.get(finding.check, "находку модели оценивает человек")
            report.skipped.append(Skipped(finding=finding, reason=reason))
            continue
        try:
            fixer(ctx, finding)
            report.applied.append(finding)
        except _CannotFix as why:
            report.skipped.append(Skipped(finding=finding, reason=str(why)))
    if ctx.doomed:
        ctx.deck.slides = [s for s in ctx.deck.slides if s.index not in ctx.doomed]
        for position, slide in enumerate(ctx.deck.slides):
            slide.index = position
    return report


__all__ = ["FixReport", "NOT_AUTOMATIC", "Skipped", "apply_fixes", "fixable"]
