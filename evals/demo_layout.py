"""Manual demo: compose a small hand-built `DeckContent` onto a real template.

Unlike `demo_content.py`, this stage makes no LLM call, so it needs no API
key and always runs live:

    uv run python evals/demo_layout.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from generator.content import DeckContent, SlideContent
from layout import compose_deck
from parser import parse

TEMPLATE_PATH = Path(__file__).parent / "templates" / "portrait-regiona.pptx"


def _build_demo_content() -> DeckContent:
    return DeckContent(
        slides=[
            SlideContent(
                role="TITLE",
                title="Engineering Offsite: Fixing Q4 Delivery Velocity",
            ),
            SlideContent(
                role="TITLE_AND_BODY",
                title="Why now",
                bullets=[
                    "Delivery velocity dropped 30% over the last two quarters.",
                    "Misalignment between teams costs more time than any single project.",
                    "Technical debt is now the top blocker cited in retros.",
                    "Competitors are shipping faster with smaller teams.",
                    "The cost of doing nothing compounds every sprint.",
                    "Three focused days can reset the trajectory before Q1.",
                    "Leadership alignment now avoids a much larger fire later.",
                ],
                body=(
                    "This offsite is not a retreat — it is three days of structured work "
                    "sessions targeting the specific blockers identified in the last two "
                    "retros, with concrete deliverables at the end of each day."
                ),
            ),
            SlideContent(
                role="TITLE_AND_BODY",
                title="What the three days produce",
                table=[
                    ["Day", "Focus", "Deliverable"],
                    ["1", "Alignment", "Shared roadmap priorities"],
                    ["2", "Tech debt", "Prioritized paydown backlog"],
                    ["3", "Process", "Revised sprint rituals"],
                ],
            ),
        ]
    )


def main() -> int:
    deck = parse(TEMPLATE_PATH)
    deck_content = _build_demo_content()

    for variant in ("compact", "standard", "detailed"):
        composed = compose_deck(deck_content, deck, variant)
        print(f"\n=== variant: {variant} ===")
        for i, slide in enumerate(composed.slides, start=1):
            print(f"{i:2d}. [{slide.layout_name}] {len(slide.shapes)} shapes")
            for shape in slide.shapes:
                if shape.kind == "text_box" and shape.paragraphs:
                    text = " | ".join(
                        "".join(run.text for run in p.runs) for p in shape.paragraphs
                    )
                    print(
                        f"      text_box ({shape.placeholder_type}, "
                        f"{len(shape.paragraphs)} paragraphs): {text[:120]}"
                    )
                elif shape.kind == "table":
                    print(f"      table: {len(shape.rows)} rows")
                elif shape.kind == "picture":
                    print("      picture: untouched")

    return 0


if __name__ == "__main__":
    sys.exit(main())
