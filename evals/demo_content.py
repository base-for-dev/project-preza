"""Manual demo: generate full slide content for a real parsed template.

Not a test — run it by hand once you've put your OpenRouter key in `.env`:

    uv run python evals/demo_content.py

Guarded to only make a live call if INFERENCE_API_KEY is set, since this
environment has no key and content generation needs a real LLM call.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from design_system import extract_design_system
from generator import generate_content, generate_outline
from parser import parse

TEMPLATE_PATH = Path(__file__).parent / "templates" / "portrait-regiona.pptx"

BRIEF = (
    "Pitch a 3-day offsite for the engineering team to leadership: why it's worth the "
    "budget, what we'll do, and the expected impact on Q4 delivery velocity."
)
SLIDE_COUNT = 10


def main() -> int:
    if not os.environ.get("INFERENCE_API_KEY"):
        print("Set INFERENCE_API_KEY in .env to run this live.")
        return 0

    deck = parse(TEMPLATE_PATH)
    design_system = extract_design_system(deck)

    outline = generate_outline(
        BRIEF, slide_count=SLIDE_COUNT, available_patterns=design_system.patterns
    )
    content = generate_content(outline, design_system.patterns, BRIEF)

    for i, slide in enumerate(content.slides, start=1):
        print(f"{i:2d}. [{slide.role}] {slide.title}")
        for bullet in slide.bullets:
            print(f"    - {bullet}")
        if slide.body:
            print(f"    body: {slide.body}")
        if slide.table:
            print(f"    table: {slide.table}")
        if slide.image_brief:
            print(f"    image_brief: {slide.image_brief}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
