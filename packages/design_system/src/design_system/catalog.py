"""Per-slide template catalog: which template slides to build on, and for what.

A template's *layouts* often say nothing about its slides: Canva/SlidesGo
packs put every slide on one blank layout, and organizer templates mix real
content slides with instruction slides ("use slide 7 for the title", colour
swatches, logo sheets) on the same layout. Choosing by layout name then picks
slides at random — including the instructions.

A `SlideCatalog` records, per template slide, whether it's usable for
content, its purpose, and a one-line description. It's produced once per
template at preparation time (an LLM reads every slide — see
`brand.catalog`), cached, and applied here deterministically: `apply_catalog`
turns the template into a deck whose every usable slide is its own "layout"
named after its purpose, so the rest of the pipeline (outline roles,
`pick_template_slides`, composition, audit) picks exact slides unchanged.
"""

from __future__ import annotations

import re

from ir_schema import Deck
from pydantic import BaseModel, Field

# Purposes a catalog entry may carry. Free text from the model is normalized
# onto this list; anything else becomes "content".
PURPOSES = (
    "title", "agenda", "section", "problem", "solution", "features", "stats",
    "steps", "timeline", "comparison", "team", "demo", "quote", "image",
    "content", "contacts", "closing",
)


class SlideCatalogEntry(BaseModel):
    index: int  # the template slide's own `Slide.index` (0-based)
    usable: bool = True
    purpose: str = "content"
    description: str = ""


class SlideCatalog(BaseModel):
    entries: list[SlideCatalogEntry] = Field(default_factory=list)


def role_name(entry: SlideCatalogEntry) -> str:
    """Stable, copyable role id: purpose plus 1-based slide number ("team-09")."""
    return f"{entry.purpose}-{entry.index + 1:02d}"


def normalize_catalog(catalog: SlideCatalog, deck: Deck) -> SlideCatalog:
    """One entry per template slide, purposes clamped to `PURPOSES`.

    Slides the model skipped are kept as usable "content" — a missing entry
    must not silently drop a real slide. A catalog marking *every* slide
    unusable is treated as broken, and everything stays usable.
    """
    by_index = {e.index: e for e in catalog.entries}
    entries = []
    for slide in deck.slides:
        entry = by_index.get(slide.index, SlideCatalogEntry(index=slide.index))
        purpose = re.sub(r"[^a-z]", "", entry.purpose.lower())
        entries.append(
            entry.model_copy(
                update={"purpose": purpose if purpose in PURPOSES else "content"}
            )
        )
    if entries and not any(e.usable for e in entries):
        entries = [e.model_copy(update={"usable": True}) for e in entries]
    return SlideCatalog(entries=entries)


def apply_catalog(deck: Deck, catalog: SlideCatalog) -> tuple[Deck, dict[str, str]]:
    """Usable slides only, each renamed to its own role; plus role -> description.

    Never mutates `deck`.
    """
    catalog = normalize_catalog(catalog, deck)
    by_index = {e.index: e for e in catalog.entries}
    slides = []
    descriptions: dict[str, str] = {}
    for slide in deck.slides:
        entry = by_index[slide.index]
        if not entry.usable:
            continue
        role = role_name(entry)
        slides.append(slide.model_copy(update={"layout_name": role}, deep=True))
        descriptions[role] = entry.description
    return deck.model_copy(update={"slides": slides}), descriptions
