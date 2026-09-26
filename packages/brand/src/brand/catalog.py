"""Template -> `SlideCatalog`: an LLM reads every slide once, at preparation time.

Part of the brand-pack preparation stage (unbounded time), not of generation:
the result is cached per template file and applied deterministically by
`design_system.apply_catalog`. See that module for why per-slide cataloguing
beats choosing by layout name.
"""

from __future__ import annotations

from design_system import SlideCatalog, describe_slots, normalize_catalog
from generator.structure import describe_structure
from inference import InferenceClient, load_skill
from ir_schema import AutoShape, Deck, Picture, Table, TextBoxShape

# Slides per cataloguing call. Big organizer templates run to 40+ slides;
# batches keep each reply well inside max_tokens.
BATCH = 20
ROW_TEXT_CHARS = 220


def catalog_rows(deck: Deck, indexes: list[int] | None = None) -> str:
    """Each template slide as one prompt row: number, layout, structure, text.

    Enough for the model to tell an instruction slide ("Используй для
    оформления слайд 7") from a real one, without any geometry.
    """
    rows = []
    for slide in deck.slides:
        if indexes is not None and slide.index not in indexes:
            continue
        texts: list[str] = []
        pictures = 0
        for shape in slide.shapes:
            if isinstance(shape, (TextBoxShape, AutoShape)):
                text = " ".join(
                    "".join(run.text for run in p.runs) for p in shape.paragraphs
                ).strip()
                if text:
                    texts.append(text)
            elif isinstance(shape, Table):
                texts.append("[table]")
            elif isinstance(shape, Picture):
                pictures += 1
        text = " | ".join(texts)
        if len(text) > ROW_TEXT_CHARS:
            text = text[:ROW_TEXT_CHARS] + "…"
        rows.append(
            f"#{slide.index + 1} layout: {slide.layout_name!r} | "
            f"structure: {describe_structure(describe_slots(slide))} | "
            f"pictures: {pictures} | text: {text or '(none)'}"
        )
    return "\n".join(rows)


def build_slide_catalog(deck: Deck, *, client: InferenceClient | None = None) -> SlideCatalog:
    """Catalogue every slide of `deck` (batched LLM calls), normalized.

    Slide numbers in the prompt and reply are 1-based, as a person reads the
    template; entries store the 0-based `Slide.index`.
    """
    skill = load_skill("template-catalog")
    inference_client = client or InferenceClient()
    indexes = [s.index for s in deck.slides]
    entries = []
    for start in range(0, len(indexes), BATCH):
        batch = indexes[start : start + BATCH]
        reply = inference_client.complete_structured(
            model=skill.model,
            system_prompt=skill.prompt,
            user_content=(
                f"Template slides:\n{catalog_rows(deck, batch)}\n\n"
                'Respond with JSON: {"entries": [{"index": <slide number as shown after #>, '
                '"usable": true|false, "purpose": ..., "description": ...}, ...]} '
                f"— one entry for each of the {len(batch)} slides above."
            ),
            temperature=skill.temperature,
            max_tokens=skill.max_tokens,
            fallback_models=skill.fallback_models,
            timeout=skill.timeout,
            response_model=SlideCatalog,
        )
        for entry in reply.entries:
            # 1-based in the prompt -> 0-based Slide.index.
            entries.append(entry.model_copy(update={"index": entry.index - 1}))
    return normalize_catalog(SlideCatalog(entries=entries), deck)
