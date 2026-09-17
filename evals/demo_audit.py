"""Manual demo: compose a small hand-built `DeckContent` onto a real template,
then run the deterministic audit checks against it.

Like `demo_layout.py`, this makes no LLM call, so it needs no API key and
always runs live:

    uv run python evals/demo_audit.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

from audit import run_checks
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
        findings = run_checks(composed, deck)

        print(f"\n=== variant: {variant} — {len(findings)} finding(s) ===")
        by_check = defaultdict(list)
        for finding in findings:
            by_check[finding.check].append(finding)

        if not by_check:
            print("  (no findings)")
            continue

        for check, items in sorted(by_check.items()):
            print(f"  {check} ({len(items)}):")
            for f in items:
                print(f"    slide {f.slide_index} shape {f.shape_id}: {f.message}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
