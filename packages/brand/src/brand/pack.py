"""Brand content pack -> `BrandContext`, built once ahead of any generation.

A content pack is whatever a company can hand over about how it presents
itself: `.pptx` templates, brand books and past decks (PDF/DOCX/MD), logos
and images, font files. This is the *preparation* stage — it may take as long
as it needs (several LLM calls over every document), because its output is
saved to disk and reused by every later generation, which must fit in five
minutes.

What comes out, and where each part is used later:
- tokens (palette, fonts) — straight from `design_system` on each template;
  they already drive layout, and are listed in prompts so writing matches.
- entities (product names, team, partners, terms) — canonical spellings the
  writer must use.
- voice (tone rules, do/don't, signature phrases) — how the company talks.
- assets (logos, images, font files) — catalogued for the UI and future use.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from design_system import extract_design_system
from inference import InferenceClient, load_skill
from ingest import extract_text
from parser.parser import parse
from pydantic import BaseModel, Field

# Text a template addresses to *its user* — greetings, fill-in instructions,
# placeholders — is guidance, not the brand's voice. Seen live: an
# organizer template's "Привет, участник!" / "Удачи!" extracted as signature
# phrases and then spoken in a finalist's talk.
_TEMPLATE_GUIDANCE = re.compile(
    r"привет|удач|добро пожаловать|участник|\bты\b|\bтво[йеияю]|\bтебе\b"
    r"|используй|расскажи|опиши|укажи|вставь|заполни|добавь|замени"
    r"|lorem|click to|insert|your (logo|team|text|name)|add your|placeholder",
    re.IGNORECASE,
)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"}
FONT_SUFFIXES = {".ttf", ".otf", ".woff", ".woff2"}
TEMPLATE_SUFFIX = ".pptx"

# One extraction call's worth of brand text. Prep time is unbounded, so big
# packs are simply split into more calls rather than truncated.
CHUNK_CHARS = 20_000
MAX_CHUNKS = 12


class BrandEntity(BaseModel):
    name: str
    kind: str = ""  # product / company / team / person / event / term / ...
    description: str = ""


class BrandVoice(BaseModel):
    tone: list[str] = Field(default_factory=list)
    do: list[str] = Field(default_factory=list)
    dont: list[str] = Field(default_factory=list)
    signature_phrases: list[str] = Field(default_factory=list)


class BrandExtraction(BaseModel):
    """One extraction call's output (per chunk of brand text)."""

    entities: list[BrandEntity] = Field(default_factory=list)
    voice: BrandVoice = Field(default_factory=BrandVoice)
    # A deck structure the material prescribes or recommends (organizers'
    # "your final pitch must cover: problem, solution, demo, team..."), in
    # order. Empty when the material doesn't prescribe one.
    structure: list[str] = Field(default_factory=list)


class BrandContext(BaseModel):
    id: str
    name: str
    template_files: list[str] = Field(default_factory=list)
    palette: list[str] = Field(default_factory=list)
    fonts: list[str] = Field(default_factory=list)
    font_files: list[str] = Field(default_factory=list)
    logos: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)
    entities: list[BrandEntity] = Field(default_factory=list)
    voice: BrandVoice = Field(default_factory=BrandVoice)
    structure: list[str] = Field(default_factory=list)

    def prompt_text(self) -> str:
        """Compact brand block for generation prompts (kept under ~2k chars)."""
        lines = [f"Brand: {self.name}"]
        if self.structure:
            lines.append("Recommended deck structure (cover these, in this order):")
            lines.extend(f"{i}. {step}" for i, step in enumerate(self.structure[:10], start=1))
        if self.entities:
            lines.append("Names and terms (use exactly these spellings):")
            lines.extend(
                f"- {e.name}" + (f" — {e.description}" if e.description else "")
                for e in self.entities[:15]
            )
        voice = _without_guidance(self.voice)
        if voice.tone:
            lines.append("Tone: " + "; ".join(voice.tone[:6]))
        if voice.do:
            lines.append("Do: " + "; ".join(voice.do[:6]))
        if voice.dont:
            lines.append("Don't: " + "; ".join(voice.dont[:6]))
        if voice.signature_phrases:
            lines.append(
                "Signature phrasing (reuse only where it fits naturally; never as a title): "
                + " / ".join(voice.signature_phrases[:6])
            )
        if self.fonts:
            lines.append("Brand fonts: " + ", ".join(self.fonts[:4]))
        return "\n".join(lines)[:2_000]


def build_brand_context(
    pack_id: str,
    name: str,
    files: list[Path],
    *,
    client: InferenceClient | None = None,
) -> BrandContext:
    """Sort a pack's files by kind, extract tokens and brand voice, merge into one context."""
    templates = [f for f in files if f.suffix.lower() == TEMPLATE_SUFFIX]
    fonts = [f for f in files if f.suffix.lower() in FONT_SUFFIXES]
    images = [f for f in files if f.suffix.lower() in IMAGE_SUFFIXES]
    logos = [f for f in images if "logo" in f.stem.lower() or "лого" in f.stem.lower()]
    documents = [f for f in files if f not in templates + fonts + images]

    palette: list[str] = []
    font_names: list[str] = []
    for template in templates:
        try:
            design = extract_design_system(parse(template))
        except Exception:
            continue
        palette += [c.value for c in design.palette if c.kind == "rgb"]
        # "+mj-lt"/"+mn-lt" are theme-font references, not font names.
        font_names += [f.name for f in design.typography.fonts if not f.name.startswith("+")]
    font_names += [_font_family(f) for f in fonts]

    texts = [t for f in [*documents, *templates] if (t := extract_text(f))]
    extraction = _extract_voice(texts, client) if texts else BrandExtraction()

    return BrandContext(
        id=pack_id,
        name=name,
        template_files=[f.name for f in templates],
        palette=_unique(palette)[:10],
        fonts=_unique(font_names)[:6],
        font_files=[f.name for f in fonts],
        logos=[f.name for f in logos],
        images=[f.name for f in images if f not in logos],
        documents=[f.name for f in documents],
        entities=extraction.entities,
        voice=extraction.voice,
        structure=extraction.structure,
    )


def _font_family(path: Path) -> str:
    """"Inter-SemiBold.ttf" -> "Inter" — good enough without parsing the font file."""
    return path.stem.split("-")[0].split("_")[0]


def _chunks(texts: list[str]) -> list[str]:
    joined = "\n\n---\n\n".join(t.strip() for t in texts if t.strip())
    return [joined[i : i + CHUNK_CHARS] for i in range(0, len(joined), CHUNK_CHARS)][:MAX_CHUNKS]


def _extract_voice(texts: list[str], client: InferenceClient | None) -> BrandExtraction:
    skill = load_skill("brand-extraction")
    inference_client = client or InferenceClient()

    def run(chunk: str) -> BrandExtraction:
        return inference_client.complete_structured(
            model=skill.model,
            system_prompt=skill.prompt,
            user_content=(
                f"Brand material:\n{chunk}\n\n"
                'Respond with JSON: {"structure": [...], "entities": [{"name": ..., '
                '"kind": ..., "description": ...}], "voice": {"tone": [...], '
                '"do": [...], "dont": [...], "signature_phrases": [...]}}'
            ),
            temperature=skill.temperature,
            max_tokens=skill.max_tokens,
            fallback_models=skill.fallback_models,
            timeout=skill.timeout,
            response_model=BrandExtraction,
        )

    results: list[BrandExtraction] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in [pool.submit(run, c) for c in _chunks(texts)]:
            try:
                results.append(future.result())
            except Exception:
                # One failed chunk loses that chunk's facts, not the whole pack.
                continue
    return merge_extractions(results)


def merge_extractions(results: list[BrandExtraction]) -> BrandExtraction:
    """Union of per-chunk results: entities deduped by name, voice lists deduped."""
    entities: dict[str, BrandEntity] = {}
    for result in results:
        for entity in result.entities:
            key = entity.name.strip().lower()
            if key and (key not in entities or len(entity.description) > len(entities[key].description)):
                entities[key] = entity
    voice = BrandVoice(
        tone=_unique(t for r in results for t in r.voice.tone)[:8],
        do=_unique(t for r in results for t in r.voice.do)[:8],
        dont=_unique(t for r in results for t in r.voice.dont)[:8],
        signature_phrases=_unique(t for r in results for t in r.voice.signature_phrases)[:10],
    )
    # Structure isn't merged item-by-item — two chunks' recommended orders
    # can't be interleaved meaningfully. The longest one wins.
    structure = max((r.structure for r in results), key=len, default=[])
    return BrandExtraction(
        entities=list(entities.values())[:30], voice=_without_guidance(voice), structure=structure
    )


def _without_guidance(voice: BrandVoice) -> BrandVoice:
    """Voice minus lines that are a template talking to its user."""

    def keep(items: list[str]) -> list[str]:
        return [i for i in items if not _TEMPLATE_GUIDANCE.search(i)]

    return BrandVoice(
        tone=voice.tone,
        do=voice.do,
        dont=voice.dont,
        signature_phrases=keep(voice.signature_phrases),
    )


def _unique(items) -> list[str]:
    seen: dict[str, str] = {}
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen[key] = item.strip()
    return list(seen.values())
