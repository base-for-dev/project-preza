"""Proves `extract_design_system` generalizes across templates it has never
seen tuned for — the requirement ARCHITECTURE.md calls out as the thing this
package either enforces or violates.

Runs against all 5 real templates dropped into `evals/templates/` (gitignored,
see `evals/README.md`) rather than synthetic fixtures: a design_system
extractor that only works on hand-crafted input hasn't proven anything.

    uv run pytest packages/design_system -v -s
"""

from __future__ import annotations

from pathlib import Path

import pytest
from design_system import extract_design_system
from parser import parse

TEMPLATES_DIR = Path(__file__).parents[2].parent / "evals" / "templates"

TEMPLATE_FILES = [
    "portrait-regiona.pptx",
    "lct2026.pptx",
    "vk-workspace-conf.pptx",
    "vk-education.pptx",
    "vktech.pptx",
]


def _available_templates() -> list[str]:
    return [name for name in TEMPLATE_FILES if (TEMPLATES_DIR / name).exists()]


pytestmark = pytest.mark.skipif(
    not _available_templates(),
    reason=f"no templates found in {TEMPLATES_DIR} (see evals/README.md)",
)


@pytest.mark.parametrize("filename", _available_templates())
def test_extract_design_system_generalizes(filename: str):
    path = TEMPLATES_DIR / filename
    deck = parse(path)

    design_system = extract_design_system(deck)

    total_slide_count = len(deck.slides)
    pattern_slide_count = sum(p.slide_count for p in design_system.patterns)

    print(
        f"\n{filename}: "
        f"palette={len(design_system.palette)} colors, "
        f"fonts={len(design_system.typography.fonts)}, "
        f"type_scale={[t.size_pt for t in design_system.typography.type_scale]}, "
        f"patterns={len(design_system.patterns)} "
        f"({[(p.layout_name, p.slide_count) for p in design_system.patterns]})"
    )

    assert design_system.patterns, "expected at least one layout pattern"
    assert pattern_slide_count == total_slide_count, (
        f"pattern slide counts ({pattern_slide_count}) must sum to the deck's "
        f"total slide count ({total_slide_count})"
    )

    for pattern in design_system.patterns:
        assert pattern.shape_summaries, f"pattern {pattern.layout_name!r} has no shape summaries"

    # Palette/typography are allowed to be empty for a template with no text
    # or fills at all, but every template evaluated here has real content, so
    # require non-empty output to catch a broken extractor rather than a
    # legitimately blank deck.
    assert design_system.palette, f"{filename}: expected a non-empty color palette"
    assert design_system.typography.fonts, f"{filename}: expected at least one font"
    assert design_system.typography.type_scale, f"{filename}: expected a non-empty type scale"
