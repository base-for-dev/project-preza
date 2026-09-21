"""Plain-language descriptions of slide structure, for LLM prompts.

The models pick layouts and size their writing from these strings, so they say
concretely what the slide can hold ("exactly 3 parallel cards") rather than
restating a layout name that carries no meaning on its own.
"""

from __future__ import annotations

from design_system import SlotSummary


def describe_structure(slots: SlotSummary | None) -> str:
    """One-line structural description of what a slide can hold."""
    if slots is None:
        return "structure unknown (use judgment)"

    if slots.kind == "cards":
        core = f"{slots.card_slots} parallel cards (each holds one short item)"
    elif slots.kind == "table":
        core = "a data table"
    elif slots.kind == "body":
        core = (
            "one text area (bullet list or short paragraph)"
            if slots.body_slots == 1
            else f"{slots.body_slots} separate text areas"
        )
    else:
        core = "a title only (no body text)"

    extras = []
    if slots.has_table and slots.kind != "table":
        extras.append("a table")
    if slots.has_picture:
        extras.append("a picture")
    tail = f", plus {' and '.join(extras)}" if extras else ""
    if slots.has_title and slots.kind != "title_only":
        return f"title + {core}{tail}"
    return core + tail
