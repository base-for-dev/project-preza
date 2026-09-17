"""Manual demo: generate an outline for a real parsed template.

Not a test — run it by hand once you've put your OpenRouter key in `.env`:

    uv run python evals/demo_outline.py

Guarded to only make a live call if INFERENCE_API_KEY is set, since this
environment has no key and outline generation needs a real LLM call.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from generator import generate_outline
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
    available_patterns = sorted({slide.layout_name for slide in deck.slides})

    outline = generate_outline(
        BRIEF, slide_count=SLIDE_COUNT, available_patterns=available_patterns
    )

    for i, slide in enumerate(outline.slides, start=1):
        print(f"{i:2d}. [{slide.role}] {slide.summary}")
        print(f"    intent: {slide.intent}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
