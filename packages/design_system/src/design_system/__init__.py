"""IR -> design tokens + layout patterns.

Single entry point: `extract_design_system(deck)`. See `tokens.py` for color/
typography extraction and `patterns.py` for slide-role pattern
classification — both are purely structural/statistical over the IR, with no
template-specific assumptions (ARCHITECTURE.md's generalization requirement).
"""

from __future__ import annotations

from ir_schema import Deck
from pydantic import BaseModel

from design_system.figures import figures
from design_system.patterns import LayoutPattern, ShapeSummary, extract_patterns
from design_system.slots import (
    SlotSummary,
    classify_shapes,
    describe_slots,
    is_body_placeholder,
    is_functional_chrome,
    is_non_content_shape,
    is_title,
    pick_template_slides,
    placeholder_kind,
    repeated_slot_groups,
    representative_slots,
    shape_has_text,
)
from design_system.textfit import apply_factor, estimate_text_height, fit_factor
from design_system.tokens import (
    ColorToken,
    FontToken,
    SizeToken,
    Typography,
    extract_colors,
    extract_typography,
)


class DesignSystem(BaseModel):
    palette: list[ColorToken]
    typography: Typography
    patterns: list[LayoutPattern]


def extract_design_system(deck: Deck) -> DesignSystem:
    """Extract design tokens and slide-role layout patterns from a parsed `Deck`."""
    return DesignSystem(
        palette=extract_colors(deck),
        typography=extract_typography(deck),
        patterns=extract_patterns(deck),
    )


__all__ = [
    "ColorToken",
    "apply_factor",
    "estimate_text_height",
    "fit_factor",
    "classify_shapes",
    "figures",
    "FontToken",
    "SizeToken",
    "Typography",
    "LayoutPattern",
    "ShapeSummary",
    "SlotSummary",
    "DesignSystem",
    "describe_slots",
    "is_body_placeholder",
    "is_functional_chrome",
    "is_non_content_shape",
    "is_title",
    "pick_template_slides",
    "placeholder_kind",
    "repeated_slot_groups",
    "representative_slots",
    "shape_has_text",
    "extract_design_system",
    "extract_colors",
    "extract_typography",
    "extract_patterns",
]
