"""Round-trip eval: template.pptx -> IR -> pptx, diffed against the original.

    uv run python evals/roundtrip_check.py [path/to/template.pptx]

Parses the source file, exports the IR straight back to `.pptx`, re-parses
that output, and diffs slide count / shape count / text content between the
two parses. Passthrough shapes (charts, SmartArt, groups, ...) are expected
to disappear on export -- that's reported separately, not counted as a
failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = REPO_ROOT / "evals" / "templates" / "portrait-regiona.pptx"
OUTPUT_DIR = REPO_ROOT / "evals" / "output"

from export import export_pptx  # noqa: E402
from ir_schema import PassthroughShape, Slide  # noqa: E402
from parser import parse  # noqa: E402


def shape_text(shape) -> str:
    if isinstance(shape, PassthroughShape):
        return ""
    if hasattr(shape, "paragraphs"):
        return "\n".join(
            "".join(run.text for run in paragraph.runs) for paragraph in shape.paragraphs
        )
    if hasattr(shape, "rows"):
        return "\n".join(cell.text for row in shape.rows for cell in row)
    return ""


def slide_texts(slide: Slide) -> list[str]:
    return [shape_text(shape) for shape in slide.shapes]


def check_slide(original: Slide, roundtripped: Slide) -> tuple[bool, list[str]]:
    problems = []

    passthrough_count = sum(
        1 for shape in original.shapes if isinstance(shape, PassthroughShape)
    )
    expected_shape_count = len(original.shapes) - passthrough_count

    if len(roundtripped.shapes) != expected_shape_count:
        problems.append(
            f"shape count {len(roundtripped.shapes)} != expected {expected_shape_count} "
            f"(original had {len(original.shapes)}, {passthrough_count} passthrough)"
        )

    original_texts = [t for t in slide_texts(original) if t]
    roundtripped_texts = [t for t in slide_texts(roundtripped) if t]
    if original_texts != roundtripped_texts:
        problems.append(f"text mismatch: {original_texts!r} != {roundtripped_texts!r}")

    if passthrough_count:
        problems.append(f"note: {passthrough_count} passthrough shape(s) correctly skipped")

    is_pass = not any(not p.startswith("note:") for p in problems)
    return is_pass, problems


def run(template_path: Path) -> bool:
    original_deck = parse(template_path)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{template_path.stem}-roundtrip.pptx"
    export_pptx(original_deck, out_path)

    roundtripped_deck = parse(out_path)

    print(f"source:     {template_path}")
    print(f"roundtrip:  {out_path}")
    print()

    overall_pass = True

    if len(original_deck.slides) != len(roundtripped_deck.slides):
        print(
            f"FAIL slide count: {len(original_deck.slides)} -> "
            f"{len(roundtripped_deck.slides)}"
        )
        overall_pass = False
    else:
        print(f"slide count: {len(original_deck.slides)} (match)")

    print()
    for original_slide, roundtripped_slide in zip(
        original_deck.slides, roundtripped_deck.slides, strict=True
    ):
        is_pass, problems = check_slide(original_slide, roundtripped_slide)
        overall_pass = overall_pass and is_pass
        status = "PASS" if is_pass else "FAIL"
        print(f"[{status}] slide {original_slide.index:>2} ({original_slide.layout_name})")
        for problem in problems:
            print(f"       - {problem}")

    print()
    print("RESULT:", "PASS" if overall_pass else "FAIL")
    return overall_pass


def main() -> None:
    template_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TEMPLATE
    ok = run(template_path)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
