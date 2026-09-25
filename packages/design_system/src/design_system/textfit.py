"""Text-height estimation and shrink-to-fit, shared by layout and audit.

A heuristic, not PowerPoint's layout engine: each non-empty paragraph takes
ceil(chars / chars-per-line) lines at 1.2x its font size. Layout uses it to
shrink overflowing text *in the file itself* (the exported .pptx has no
autofit, so without this the browser preview would silently shrink text that
PowerPoint then spills out of its box); audit uses the same numbers to judge.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from ir_schema import AutoShape, TextBoxShape

LINE_HEIGHT_MULTIPLIER = 1.2
PT_TO_EMU = 12700
# Fallback size for a run that inherits its size from a placeholder/theme.
DEFAULT_FONT_SIZE_PT = 18.0
# Average glyph advance as a fraction of the font size (Latin ~0.5, Cyrillic ~0.55).
AVG_CHAR_WIDTH_EM = 0.55

MIN_FONT_SIZE_PT = 8.0

SizeFn = Callable[[float], float]


def _paragraph_text(paragraph) -> str:
    return "".join(run.text for run in paragraph.runs)


def estimate_text_height(shape: TextBoxShape | AutoShape, size_fn: SizeFn | None = None) -> float:
    """EMU of height the shape's text needs; 0.0 for empty text or a single line.

    `size_fn` maps each run's size (pt) to the size to assume instead — used to
    ask "would it fit at this scale?". A single line in a box a little shorter
    than the line is cosmetic (text centres and spills a few points) and how
    many templates draw labels, so it never counts as needing more room.
    """
    total = 0.0
    total_lines = 0
    last_line_height = 0.0
    for paragraph in shape.paragraphs:
        text = _paragraph_text(paragraph).strip()
        if not text:
            continue
        sizes = [r.font_size_pt for r in paragraph.runs if r.font_size_pt is not None]
        size = max(sizes) if sizes else DEFAULT_FONT_SIZE_PT
        if size_fn is not None:
            size = size_fn(size)
        chars_per_line = max(1.0, shape.width / (size * AVG_CHAR_WIDTH_EM * PT_TO_EMU))
        lines = max(1, math.ceil(len(text) / chars_per_line))
        last_line_height = size * LINE_HEIGHT_MULTIPLIER * PT_TO_EMU
        total += lines * last_line_height
        total_lines += lines
    if total_lines <= 1 and total <= last_line_height * 1.6:
        return 0.0
    return total


_FACTORS = (0.9, 0.8, 0.7, 0.6, 0.5)
_FIT_SLACK = 1.05


def snapper(allowed: list[float], factor: float) -> SizeFn:
    """size -> the largest allowed size <= size*factor.

    Keeps shrunk text on the template's own type scale — the audit rejects
    sizes the template never uses. When the scale has nothing that small (or
    is unknown) the size just scales, to no less than `MIN_FONT_SIZE_PT`:
    text spilling out of its box is worse than one off-scale size.
    """
    ordered = sorted(allowed)

    def fn(size: float) -> float:
        target = size * factor
        fitting = [s for s in ordered if s <= target + 0.01]
        if fitting:
            return fitting[-1]
        return max(MIN_FONT_SIZE_PT, round(target * 2) / 2)

    return fn


def fit_factor(shape: TextBoxShape | AutoShape, allowed: list[float]) -> float:
    """Largest shrink factor (1.0 = untouched) at which `shape`'s text fits its box."""
    if shape.height <= 0 or estimate_text_height(shape) <= shape.height * _FIT_SLACK:
        return 1.0
    for factor in _FACTORS:
        if estimate_text_height(shape, snapper(allowed, factor)) <= shape.height * _FIT_SLACK:
            return factor
    return _FACTORS[-1]


def apply_factor(shape: TextBoxShape | AutoShape, allowed: list[float], factor: float) -> None:
    """Shrink every run in `shape` by `factor`, snapped to the template's scale."""
    if factor >= 1.0:
        return
    fn = snapper(allowed, factor)
    for paragraph in shape.paragraphs:
        for run in paragraph.runs:
            run.font_size_pt = fn(run.font_size_pt or DEFAULT_FONT_SIZE_PT)
