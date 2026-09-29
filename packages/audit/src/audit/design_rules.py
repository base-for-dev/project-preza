"""Deterministic checks on how a slide looks: colour, margins, pictures, fonts, charts.

Split from `checks.py` (bounds, density, integrity) only to keep both files
readable; both feed `run_checks`. Like every check here, the reference is the
template's own slides — never a fixed design rule of ours — except contrast,
which is a fixed accessibility rule (WCAG 2.x).

Every check skips shapes that still sit exactly where the template put them:
a template's own tight margin, off-guide logo or low-contrast badge is its
author's decision, not something generation broke.
"""

from __future__ import annotations

import base64
import io
import re

from design_system import extract_typography, shape_has_text
from ir_schema import (
    AutoShape,
    ChartShape,
    Color,
    Deck,
    PassthroughShape,
    Picture,
    Shape,
    Slide,
    Table,
    TextBoxShape,
)
from PIL import Image

from audit.finding import Finding

# --- tunables ---------------------------------------------------------------

# WCAG 2.x: 4.5:1 for normal text, 3:1 for large text (>= 24 pt, or >= 18.66 pt bold).
CONTRAST_NORMAL = 4.5
CONTRAST_LARGE = 3.0
LARGE_TEXT_PT = 24.0
LARGE_BOLD_TEXT_PT = 18.66

# margin_violation: text closer to a slide edge than this share of the slide's
# side, unless the template itself puts text that close.
MIN_MARGIN_FRACTION = 0.02
# misaligned: a moved text shape's left edge must sit within this share of the
# slide width of some left edge the template uses.
GUIDE_TOLERANCE_FRACTION = 0.01
# image_distorted: displayed aspect ratio may differ from the picture's own by this much.
ASPECT_TOLERANCE = 0.10
# slide_is_picture: one picture covering at least this share of the slide.
PICTURE_SLIDE_COVERAGE = 0.90
# brand_element_moved: how far (share of slide width/height) a template logo/footer may drift.
BRAND_DRIFT_FRACTION = 0.005
# A shape this near a slide edge, in the template, is a logo / footer / page number.
BRAND_BAND_FRACTION = 0.15
# chart_too_many_series
MAX_CHART_SERIES = 5


def _geometry(shape: Shape) -> tuple[int, int, int, int]:
    return shape.left, shape.top, shape.width, shape.height


def _template_geometries(template_deck: Deck) -> set[tuple[int, tuple[int, int, int, int]]]:
    return {(s.shape_id, _geometry(s)) for slide in template_deck.slides for s in slide.shapes}


def _is_original(shape: Shape, originals: set) -> bool:
    return (shape.shape_id, _geometry(shape)) in originals


def _visible_text_shapes(slide: Slide) -> list[TextBoxShape | AutoShape]:
    return [
        s for s in slide.shapes if isinstance(s, (TextBoxShape, AutoShape)) and shape_has_text(s)
    ]


# --- contrast ---------------------------------------------------------------


def _hex_of(color: Color | None, deck: Deck) -> str | None:
    if color is None:
        return None
    if color.kind == "rgb":
        return color.rgb
    return deck.theme_colors.get(color.theme_color or "")


def _luminance(hex_color: str) -> float:
    def channel(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(a: str, b: str) -> float:
    """WCAG contrast ratio of two 6-digit hex colours, 1.0 (none) to 21.0 (black on white)."""
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _backdrop(shape: TextBoxShape | AutoShape, slide: Slide, deck: Deck) -> str | None:
    """The solid colour behind `shape`'s text, or None when it can't be known.

    Its own fill wins; else the topmost filled shape under its centre; else the
    slide background. A picture underneath means "unknown" — never guessed.
    """
    if isinstance(shape, AutoShape) and shape.fill_color is not None:
        return _hex_of(shape.fill_color, deck)
    cx, cy = shape.left + shape.width // 2, shape.top + shape.height // 2
    under = [
        s
        for s in slide.shapes
        if s.z_order < shape.z_order
        and s.left <= cx <= s.left + s.width
        and s.top <= cy <= s.top + s.height
    ]
    for other in sorted(under, key=lambda s: s.z_order, reverse=True):
        if isinstance(other, Picture):
            return None
        if isinstance(other, AutoShape) and other.fill_color is not None:
            return _hex_of(other.fill_color, deck)
    return _hex_of(slide.background, deck)


def check_contrast(deck: Deck, template_deck: Deck) -> list[Finding]:
    """Text colour against the colour right behind it, per WCAG (AUDIT.md: контраст)."""
    originals = _template_geometries(template_deck)
    findings = []
    for slide in deck.slides:
        for shape in _visible_text_shapes(slide):
            if _is_original(shape, originals):
                continue
            backdrop = _backdrop(shape, slide, deck)
            if backdrop is None:
                continue
            worst: tuple[float, str] | None = None
            for paragraph in shape.paragraphs:
                for run in paragraph.runs:
                    fg = _hex_of(run.color, deck)
                    if fg is None or not run.text.strip():
                        continue
                    size = run.font_size_pt or 0.0
                    large = size >= LARGE_TEXT_PT or (run.bold and size >= LARGE_BOLD_TEXT_PT)
                    need = CONTRAST_LARGE if large else CONTRAST_NORMAL
                    ratio = contrast_ratio(fg, backdrop)
                    if ratio < need and (worst is None or ratio < worst[0]):
                        worst = (
                            ratio,
                            f"текст #{fg} на фоне #{backdrop}, нужно не меньше {need}:1",
                        )
            if worst:
                findings.append(
                    Finding(
                        check="low_contrast",
                        slide_index=slide.index,
                        shape_id=shape.shape_id,
                        message=f"фигура {shape.shape_id}: контраст {worst[0]:.1f}:1 — {worst[1]}",
                    )
                )
    return findings


# --- margins and guides -----------------------------------------------------


def _template_min_margin(template_deck: Deck) -> float:
    """Smallest distance (share of the slide's side) any template text has to an edge."""
    w, h = template_deck.slide_width or 1, template_deck.slide_height or 1
    margins = [1.0]
    for slide in template_deck.slides:
        for s in _visible_text_shapes(slide):
            margins += [
                s.left / w,
                s.top / h,
                (w - s.left - s.width) / w,
                (h - s.top - s.height) / h,
            ]
    return max(0.0, min(margins))


def check_margins(deck: Deck, template_deck: Deck) -> list[Finding]:
    """Text moved into the edge margin the template itself keeps clear."""
    originals = _template_geometries(template_deck)
    limit = min(MIN_MARGIN_FRACTION, _template_min_margin(template_deck))
    w, h = deck.slide_width or 1, deck.slide_height or 1
    findings = []
    for slide in deck.slides:
        for s in _visible_text_shapes(slide):
            if _is_original(s, originals):
                continue
            edges = (s.left / w, s.top / h, (w - s.left - s.width) / w, (h - s.top - s.height) / h)
            if 0 <= min(edges) < limit:  # negative = out of bounds, its own check
                findings.append(
                    Finding(
                        check="margin_violation",
                        slide_index=slide.index,
                        shape_id=s.shape_id,
                        message=(
                            f"фигура {s.shape_id} на расстоянии {min(edges):.1%} слайда от края; "
                            f"шаблон держит текст не ближе {limit:.1%}"
                        ),
                    )
                )
    return findings


def check_guides(deck: Deck, template_deck: Deck) -> list[Finding]:
    """A moved text shape whose left edge lines up with nothing the template uses."""
    originals = _template_geometries(template_deck)
    tolerance = GUIDE_TOLERANCE_FRACTION * (deck.slide_width or 1)
    guides = sorted({s.left for slide in template_deck.slides for s in _visible_text_shapes(slide)})
    if not guides:
        return []
    findings = []
    for slide in deck.slides:
        for s in _visible_text_shapes(slide):
            if _is_original(s, originals):
                continue
            if min(abs(s.left - g) for g in guides) > tolerance:
                findings.append(
                    Finding(
                        check="misaligned",
                        slide_index=slide.index,
                        shape_id=s.shape_id,
                        message=(
                            f"фигура {s.shape_id} начинается с x={s.left} EMU — это не совпадает "
                            "ни с одной направляющей шаблона"
                        ),
                    )
                )
    return findings


# --- pictures ---------------------------------------------------------------


def _pixel_size(picture: Picture) -> tuple[int, int] | None:
    """Pixel size of a picture's image, or None if it is unreadable or a single flat colour.

    A flat colour (the stand-in for a template photo with no fitting replacement)
    has no proportions to distort, so it is never measured.
    """
    if not picture.image_bytes_b64:
        return None
    try:
        with Image.open(io.BytesIO(base64.b64decode(picture.image_bytes_b64))) as image:
            if len(image.convert("RGB").getcolors(maxcolors=2) or []) == 1:
                return None
            return image.size
    except Exception:
        return None


def check_pictures(deck: Deck) -> list[Finding]:
    """Swapped-in pictures squeezed out of proportion, and slides that are one picture."""
    findings = []
    slide_area = (deck.slide_width or 1) * (deck.slide_height or 1)
    for slide in deck.slides:
        pictures = [s for s in slide.shapes if isinstance(s, Picture)]
        for pic in pictures:
            if not pic.image_replaced or pic.width <= 0 or pic.height <= 0:
                continue
            size = _pixel_size(pic)
            if size is None:
                continue
            kept_w = size[0] * (1 - pic.crop_left - pic.crop_right)
            kept_h = size[1] * (1 - pic.crop_top - pic.crop_bottom)
            if kept_w <= 0 or kept_h <= 0:
                continue
            natural, shown = kept_w / kept_h, pic.width / pic.height
            if abs(shown - natural) / natural > ASPECT_TOLERANCE:
                findings.append(
                    Finding(
                        check="image_distorted",
                        slide_index=slide.index,
                        shape_id=pic.shape_id,
                        message=(
                            f"картинка {pic.shape_id} показана в пропорции {shown:.2f}, "
                            f"а её собственная — {natural:.2f}"
                        ),
                    )
                )
        has_words = any(True for _ in _visible_text_shapes(slide)) or any(
            isinstance(s, Table) for s in slide.shapes
        )
        covering = [
            p
            for p in pictures
            if p.width * p.height >= PICTURE_SLIDE_COVERAGE * slide_area and not p.is_background
        ]
        if covering and not has_words:
            findings.append(
                Finding(
                    check="slide_is_picture",
                    slide_index=slide.index,
                    shape_id=covering[0].shape_id,
                    message="слайд — одна картинка, редактируемого текста и таблиц на нём нет",
                )
            )
    return findings


# --- template rules ---------------------------------------------------------


def check_layouts_and_fonts(deck: Deck, template_deck: Deck) -> list[Finding]:
    """Slides built on a layout the template lacks; more font families than it uses."""
    findings = []
    layouts = {s.layout_name for s in template_deck.slides}
    for slide in deck.slides:
        if slide.layout_name not in layouts:
            findings.append(
                Finding(
                    check="layout_not_from_template",
                    slide_index=slide.index,
                    message=f"макета {slide.layout_name!r} нет в шаблоне",
                )
            )
    allowed = max(2, len(extract_typography(template_deck).fonts))
    used: dict[str, int] = {}
    for slide in deck.slides:
        for s in _visible_text_shapes(slide):
            for paragraph in s.paragraphs:
                for run in paragraph.runs:
                    if run.font_name and run.text.strip():
                        used.setdefault(run.font_name, slide.index)
    if len(used) > allowed:
        extra = sorted(used, key=used.get)[allowed:]
        findings.append(
            Finding(
                check="too_many_font_families",
                slide_index=used[extra[0]],
                message=(
                    f"в колоде {len(used)} гарнитур ({', '.join(sorted(used))}), "
                    f"а шаблон использует не больше {allowed}"
                ),
            )
        )
    return findings


def check_brand_elements(deck: Deck, template_deck: Deck) -> list[Finding]:
    """Logos, footers and page numbers the template pins to the slide's edge must stay put."""
    w, h = template_deck.slide_width or 1, template_deck.slide_height or 1
    by_index = {s.index: s for s in template_deck.slides}
    findings = []
    for slide in deck.slides:
        source = by_index.get(slide.source_index if slide.source_index is not None else -1)
        if source is None:
            continue
        here = {s.shape_id: s for s in slide.shapes}
        for original in source.shapes:
            if isinstance(original, Picture) and (
                original.is_background or original.image_replaced
            ):
                continue
            cx = (original.left + original.width / 2) / w
            cy = (original.top + original.height / 2) / h
            near_edge = (
                min(cx, 1 - cx) < BRAND_BAND_FRACTION or min(cy, 1 - cy) < BRAND_BAND_FRACTION
            )
            small = original.width * original.height < 0.05 * w * h
            if not (near_edge and small) or (
                isinstance(original, (TextBoxShape, AutoShape)) and shape_has_text(original)
            ):
                continue
            moved = here.get(original.shape_id)
            if moved is None:
                continue
            drift = max(abs(moved.left - original.left) / w, abs(moved.top - original.top) / h)
            if drift > BRAND_DRIFT_FRACTION:
                findings.append(
                    Finding(
                        check="brand_element_moved",
                        slide_index=slide.index,
                        shape_id=moved.shape_id,
                        message=(
                            f"элемент {moved.shape_id} (логотип или колонтитул) сдвинут на "
                            f"{drift:.1%} слайда от места, заданного шаблоном"
                        ),
                    )
                )
    return findings


# --- charts -----------------------------------------------------------------


def _check_drawn_chart(shape: ChartShape, slide: Slide) -> list[Finding]:
    """A chart the pipeline drew: series count, units and legend it must carry."""
    findings = []
    round_chart = shape.chart_type in ("pie", "doughnut")

    def found(check: str, message: str) -> Finding:
        return Finding(
            check=check, slide_index=slide.index, shape_id=shape.shape_id, message=message
        )

    if len(shape.series) > MAX_CHART_SERIES:
        findings.append(
            found(
                "chart_too_many_series",
                f"на графике {len(shape.series)} рядов; больше {MAX_CHART_SERIES} не прочитать",
            )
        )
    if not round_chart and not shape.unit:
        findings.append(
            found("chart_missing_labels", "у графика нет единиц измерения — значения без подписи")
        )
    return findings


def check_charts(deck: Deck) -> list[Finding]:
    """Charts: series count, legend and axis titles — the template's, refilled, or drawn."""
    findings = []
    for slide in deck.slides:
        findings += [
            f
            for s in slide.shapes
            if isinstance(s, ChartShape)
            for f in _check_drawn_chart(s, slide)
        ]
        for shape in slide.shapes:
            if not (isinstance(shape, PassthroughShape) and shape.is_chart):
                continue
            series = len(re.findall(r"<c:ser>|<c:ser ", shape.raw_xml))
            rows = shape.chart_data
            if rows:
                series = max(series, len(rows[0]) - 1) if series == 0 else series
            if series > MAX_CHART_SERIES:
                findings.append(
                    Finding(
                        check="chart_too_many_series",
                        slide_index=slide.index,
                        shape_id=shape.shape_id,
                        message=(
                            f"на диаграмме {series} рядов, читается не больше {MAX_CHART_SERIES}"
                        ),
                    )
                )
            if shape.chart_data is None:
                continue  # the template's own chart, as its author labelled it
            if shape.chart_unit:
                continue  # the export writes the unit and category label onto the axes
            xml = shape.raw_xml
            has_legend = "<c:legend>" in xml or "<c:legend " in xml
            has_axis_title = bool(re.search(r"<c:(?:catAx|valAx)>.*?<c:title>", xml, re.S))
            if not has_axis_title and not (series <= 1 and "<c:title>" in xml):
                findings.append(
                    Finding(
                        check="chart_missing_labels",
                        slide_index=slide.index,
                        shape_id=shape.shape_id,
                        message="у диаграммы нет подписей осей — значения без единиц",
                    )
                )
            elif series > 1 and not has_legend:
                findings.append(
                    Finding(
                        check="chart_missing_labels",
                        slide_index=slide.index,
                        shape_id=shape.shape_id,
                        message="на диаграмме несколько рядов, а легенды нет",
                    )
                )
    return findings
