import base64
import hashlib
import json
import logging
import re
import shutil
import tempfile
import threading
import time
import urllib.parse
from collections.abc import Iterator
from pathlib import Path

import httpx
from audit import Finding, run_checks, run_model_checks
from design_system import (
    DesignSystem,
    apply_catalog,
    classify_shapes,
    describe_slots,
    extract_design_system,
    mark_visual_titles,
    pick_template_slides,
)
from export import fonts
from export.export import export_pptx
from export.render import RenderUnavailable, render_pptx, soffice_path
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from generator.content import DeckContent, generate_content
from generator.outline import Outline, finalize_outline, generate_outline, split_sections
from generator.timing import WORDS_PER_MINUTE, slide_count_for
from images import (
    OpenImageClient,
    UnsplashClient,
    apply_photos,
    apply_user_images,
    fill_empty_frames,
    find_slide_photos,
    neutralize_template_photos,
)
from inference import InferenceClient, InferenceError, QuotaExhausted
from ingest import FactSheet, digest_sources
from ir_schema import Deck
from layout import compose_deck
from parser.parser import parse
from pydantic import BaseModel

from server import storage, thumbnails
from server.context_api import build_catalog
from server.context_api import router as context_router

log = logging.getLogger(__name__)

app = FastAPI(title="project-preza server")
app.include_router(context_router)

# Dev-only: apps/web runs on a different port. Tighten this once there's a real
# deployment target — see ARCHITECTURE.md's apps/server boundary note.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

REPO_ROOT = Path(__file__).resolve().parents[4]
TEST_TEMPLATES_DIR = REPO_ROOT / "evals" / "templates"

# Template fonts (decoded from the templates, or fetched from Google Fonts)
# live with the rest of the runtime data.
fonts.CACHE_DIR = storage.DATA_DIR / "fonts"


def _discover_templates() -> dict[str, Path]:
    """id -> path for every .pptx in evals/templates/ and in every brand pack.

    Brand-pack templates get a `<pack id>:<stem>` id so they can't collide
    with loose templates and so a pack's own templates are easy to pick out.

    Includes both the sample templates that ship there (gitignored — each
    dev drops their own copies per evals/README.md) and anything uploaded
    via `POST /api/templates`. Scanned per-call rather than cached so a new
    file doesn't need a server restart to show up. The id is just the
    filename stem, so it's stable across a machine but not guaranteed
    unique in theory (two differently-cased or differently-extensioned
    files colliding) — acceptable for dev sample data.
    """
    found = {path.stem: path for path in sorted(TEST_TEMPLATES_DIR.glob("*.pptx"))}
    for pack_id, path in storage.pack_templates():
        found[f"{pack_id}:{path.stem}"] = path
    return found


def _sanitize_stem(filename: str) -> str:
    """Filesystem-safe filename stem that keeps the uploaded name intact.

    Only strips characters that are actually unsafe/reserved in a filename
    (path separators, colons, null bytes, ...) — everything else (spaces,
    Cyrillic, punctuation) survives, so the template's id/label (both
    derived from this stem, see `_discover_templates`) matches the file the
    user uploaded rather than a mangled ASCII slug.
    """
    stem = Path(filename).stem.strip()
    stem = re.sub(r'[\/\\\0:*?"<>|]', "-", stem)
    return stem or "template"


def _uploaded_template_path(template_id: str) -> Path | None:
    """The file behind an `upload:<stem>` id, or `None` if it isn't one / doesn't exist.

    Never listed in `_discover_templates()` — only reachable by an id the
    uploader's own upload response handed them (see `upload_template`).
    """
    stem = template_id.removeprefix("upload:")
    if stem == template_id:  # no "upload:" prefix at all
        return None
    path = storage.UPLOADED_TEMPLATES_DIR / f"{stem}.pptx"
    return path if path.is_file() else None


def _resolve_template_path(template_id: str) -> Path:
    uploaded = _uploaded_template_path(template_id)
    if uploaded is not None:
        return uploaded
    templates = _discover_templates()
    path = templates.get(template_id)
    if path is None:
        raise HTTPException(
            404, f"unknown template_id: {template_id!r} — available: {sorted(templates)}"
        )
    if not path.exists():
        raise HTTPException(
            404,
            f"template file missing on disk: {path.relative_to(REPO_ROOT)} "
            "— see evals/README.md to fetch sample templates locally",
        )
    return path


# parse() + extract_design_system() are deterministic in the template file
# alone, but every generation request re-ran both before the first (slow) LLM
# call. Cache the pair per (path, mtime) so repeat requests against the same
# template skip straight to inference; a swapped file (new mtime) invalidates.
_DECK_CACHE: dict[tuple[str, int], tuple[Deck, DesignSystem]] = {}


def _load_template(template_id: str) -> tuple[Deck, DesignSystem]:
    """Parsed `Deck` + its `DesignSystem`, memoized per template file version.

    When the template has a slide catalog (built at preparation time, see
    `design_system.catalog`), the returned deck is the catalogued one: only
    usable slides, each its own role named after its purpose, and the
    patterns carry each slide's description for the outline.
    """
    path = _resolve_template_path(template_id)
    catalog = storage.load_catalog(path)
    key = (str(path), path.stat().st_mtime_ns, catalog is not None)
    cached = _DECK_CACHE.get(key)
    if cached is None:
        # Headings set as plain text boxes (most templates) are titles too.
        deck = mark_visual_titles(parse(path))
        # Real per-font character widths, so slot capacity and shrink-to-fit
        # know a condensed face from a wide one (see export.fonts).
        try:
            fonts.annotate_char_widths(deck, path)
        except Exception:  # fonts only sharpen estimates; never block generation
            log.warning("could not measure fonts of %s", path, exc_info=True)
        descriptions: dict[str, str] = {}
        if catalog is not None:
            deck, descriptions = apply_catalog(deck, catalog)
        design_system = extract_design_system(deck)
        for pattern in design_system.patterns:
            pattern.description = descriptions.get(pattern.layout_name, "")
        cached = (deck, design_system)
        _DECK_CACHE[key] = cached
    return cached


# Extra topic keywords for templates whose id/filename doesn't already say
# what they're about in the brief's own language (a hand-built template, or
# one named in English while briefs are typically Russian) — layered on top
# of the id's own tokens, never a replacement for them, so a well-named
# upload still matches on its filename alone with zero configuration here.
# Word stems, not full inflected forms — "питом" catches питомец/питомцы/
# питомцев, where the full word "питомец" would miss "питомцев" (Russian
# case endings change letters at the exact point a plain substring check
# looks at, not just append a suffix).
_TEMPLATE_TOPIC_HINTS: dict[str, list[str]] = {
    "savant": ["ai", "искусственн", "интеллект", "нейросет", "assistant", "автоматизац"],
    "pawvera": ["питом", "животн", "pet", "собак", "кот", "ветеринар", "страхован"],
    "parusim-po-alomu": ["туризм", "путешеств", "квест", "экскурс"],
    "world-tourism-day": ["туризм", "путешеств", "тур", "travel", "tourism"],
    "latest-trends-in-technology": ["технолог", "тренд", "trend", "technology", "инновац"],
    "tech-brand-digital-marketing": ["маркетинг", "бренд", "marketing", "brand", "реклам"],
}

# English words in template file names (library templates are named in
# English, briefs are usually Russian) -> Russian stems a brief would use.
# Stems, not full words, for the same case-ending reason as above.
_EN_TOPIC_STEMS: dict[str, list[str]] = {
    "pitch": ["питч", "инвест", "стартап", "раунд"],
    "startup": ["стартап", "питч"],
    "business": ["бизнес", "компан"],
    "consulting": ["консалт", "консульт"],
    "marketing": ["маркетинг", "продвижен", "реклам"],
    "market": ["рынок", "рынк", "рыноч"],
    "research": ["исследован", "анализ"],
    "analysis": ["анализ", "аналит"],
    "data": ["данн", "аналит", "data"],
    "science": ["наук", "исследован"],
    "tech": ["технолог", "it", "разработ"],
    "branding": ["бренд"],
    "brand": ["бренд"],
    "blockchain": ["блокчейн", "крипт", "web3"],
    "cryptocurrency": ["крипт", "биткоин"],
    "healthcare": ["медицин", "здоров", "клиник"],
    "real": ["недвиж"],
    "estate": ["недвиж", "квартир"],
    "investment": ["инвест"],
    "stocks": ["акци", "бирж", "трейд"],
    "trading": ["трейд", "бирж"],
    "project": ["проект"],
    "roadmap": ["дорожн", "план", "этап"],
    "goal": ["цел"],
    "portfolio": ["портфел"],
    "plan": ["план"],
    "sales": ["продаж"],
    "law": ["юрид", "прав", "закон"],
    "communication": ["коммуникац", "pr"],
    "conference": ["конференц", "форум"],
    "meeting": ["встреч", "совещан"],
    "agenda": ["повестк"],
    "charity": ["благотвор", "нко", "фонд"],
    "event": ["мероприят", "событ"],
    "product": ["продукт"],
    "launch": ["запуск"],
    "commerce": ["e-commerce", "интернет-магазин", "маркетплейс"],
    "electronics": ["электрон", "гаджет"],
    "architecture": ["архитект"],
    "training": ["обучен", "курс", "тренинг"],
    "report": ["отчёт", "отчет"],
    "mckinsey": ["стратег", "консалт"],
    "strategic": ["стратег"],
}

# Every brief in this app's own composer starts "Презентация про ..." (or
# the English "presentation"/"deck") — a filename token this generic isn't a
# topic signal, it's just noise that would make any template whose name
# happens to contain it (e.g. a file literally named "Презентация X.pptx")
# win by default on every request. Same reasoning for "шаблон"/"template".
_GENERIC_FILENAME_WORDS = {
    "презентация",
    "презентации",
    "презентацию",
    "шаблон",
    "шаблона",
    "template",
    "presentation",
    "design",
    "deck",
    "ppt",
    "pptx",
}


def _choose_template(brief: str) -> str:
    """Best-effort topic match between the brief and an available template.

    No LLM call — same "keyword scan, no black box" discipline as
    `detectDensity` on the frontend. Scores every available template by how
    many of its keywords (topic hints if it has any, else its own id split
    on `-`/`_`/space, minus generic filler words) appear in the brief;
    highest score wins, ties go to whichever sorts first. Zero matches
    anywhere falls back to the first available template rather than
    guessing semantically.
    """
    available = sorted(_discover_templates())
    if not available:
        raise HTTPException(404, "no templates available")

    text = brief.lower()
    best_id = available[0]
    best_score = 0
    for template_id in available:
        tokens = [
            w
            for w in re.split(r"[-_\s]+", template_id.lower())
            if w and w not in _GENERIC_FILENAME_WORDS and len(w) >= 3
        ]
        keywords = _TEMPLATE_TOPIC_HINTS.get(template_id) or [
            *tokens,
            *(stem for w in tokens for stem in _EN_TOPIC_STEMS.get(w, [])),
        ]
        score = sum(1 for kw in keywords if kw and kw in text)
        if score > best_score:
            best_id, best_score = template_id, score
    return best_id


# One photo-search client for the process: Unsplash when a key is configured,
# otherwise keyless open image search (Openverse, then Wikimedia Commons).
_UNSPLASH_CLIENT = UnsplashClient()
_PHOTO_CLIENT = _UNSPLASH_CLIENT if _UNSPLASH_CLIENT.configured else OpenImageClient()


def _compose_variants(
    content: DeckContent, deck: Deck, images: list[tuple[str, str]] | None = None
) -> dict[str, Deck]:
    """All 3 density variants, with real on-topic photos swapped in where asked.

    Composition itself (`compose_deck`) never makes a network call — image
    search is a separate, best-effort step layered on top: every photo slot
    (template photos, photo-filled shapes, empty picture frames) gets its own
    on-topic photo, and any template photo still original after it (no hit)
    becomes a flat colour — the finished deck never shows the template's
    stock photos. Empty picture frames get the talk's own images (repo
    screenshots) first. Photos are searched once and
    shared by all three variants — they differ only in text, not in slides
    or picture frames — so one generation costs one search per slide, not
    three.
    """
    variants = {}
    for name in ("compact", "standard", "detailed"):
        # The user's images where the writer put them; the rest into empty frames.
        composed = compose_deck(content, deck, name)
        composed, unused = apply_user_images(composed, content, images or [])
        variants[name] = fill_empty_frames(composed, unused)
    photos = find_slide_photos(variants["standard"], content, _PHOTO_CLIENT)
    variants = {name: apply_photos(variant, photos) for name, variant in variants.items()}
    return {name: neutralize_template_photos(variant) for name, variant in variants.items()}


DEMO_BRIEF = (
    "A 3-day engineering offsite to fix Q4 delivery velocity. Audience: "
    "engineering leadership deciding whether to approve the budget. Argue "
    "that misalignment and technical debt are costing more than the offsite "
    "would, and lay out what the three days actually produce."
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _ensure_sample_templates(directory: Path | None = None) -> bool:
    """Build the bundled sample templates when the library has none.

    Real template files aren't in git (`*.pptx` is ignored — size, licences), so
    a fresh clone would open to an empty picker and an "Авто" that has nothing
    to pick. `evals/generate_behance_templates.py` builds three small ones from
    code; run it once, only into an empty library. True if it generated any.
    """
    directory = directory or TEST_TEMPLATES_DIR
    if any(directory.glob("*.pptx")):
        return False
    script = REPO_ROOT / "evals" / "generate_behance_templates.py"
    if not script.is_file():
        return False
    try:
        import runpy

        namespace = runpy.run_path(str(script))
        namespace["OUT_DIR"] = directory
        namespace["main"].__globals__["OUT_DIR"] = directory
        namespace["main"]()
    except Exception:
        logging.getLogger(__name__).exception("could not build the sample templates")
        return False
    return any(directory.glob("*.pptx"))


@app.on_event("startup")
def _render_template_previews() -> None:
    _ensure_sample_templates()
    # Preparation work, off the request path: previews for the template picker.
    thumbnails.build_all_in_background(list(_discover_templates().values()))


@app.get("/api/templates")
def list_templates() -> dict:
    """Every template with its picker metadata.

    `previews` is how many preview images are ready (0 while they're still
    being rendered in the background, and permanently if the renderer isn't
    installed — see `renderer_available`); `tags` feed the picker's filters.
    """
    templates = []
    for key, path in sorted(_discover_templates().items()):
        meta = thumbnails.load_meta(path) or {}
        templates.append(
            {
                # Brand-pack templates ("<pack>:<stem>") show just their file name.
                "id": key,
                "label": key.split(":", 1)[-1],
                "previews": len(meta.get("slides", [])),
                "tags": meta.get("tags", []),
            }
        )
    return {"templates": templates, "renderer_available": soffice_path() is not None}


@app.get("/api/templates/{template_id}/slide/{index}.jpg")
def template_slide_image(template_id: str, index: int) -> FileResponse:
    """Template slide `index` exactly as the file renders (LibreOffice), for the inspector."""
    path = _resolve_template_path(template_id)
    image = thumbnails.slide_path(path, index)
    if image is None:
        thumbnails.build(path)
        image = thumbnails.slide_path(path, index)
    if image is None:
        raise HTTPException(404, "no render for this slide (LibreOffice unavailable?)")
    return FileResponse(image, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@app.get("/api/fonts.css")
def font_faces(family: list[str] = Query(default=[])) -> Response:  # noqa: B008
    """@font-face rules for the template fonts the browser asks about.

    Only fonts some template has already brought (embedded, or fetched from
    Google Fonts while preparing it) — see export.fonts. Unknown families get
    no rule and fall back in the browser as before.
    """
    css = fonts.font_css(
        family,
        lambda fam, style: f"/api/fonts/{urllib.parse.quote(fam)}/{style}.ttf",
    )
    return Response(css, media_type="text/css", headers={"Cache-Control": "max-age=3600"})


@app.get("/api/fonts/{family}/{style}.ttf")
def font_file(family: str, style: str) -> FileResponse:
    path = fonts.font_file(family, style)
    if path is None:
        raise HTTPException(404, "font not available")
    return FileResponse(path, media_type="font/ttf", headers={"Cache-Control": "max-age=86400"})


@app.get("/api/templates/{template_id}/preview/{n}")
def template_preview(template_id: str, n: int) -> FileResponse:
    """The n-th preview image of a template (0 = its cover), rendered on demand if needed."""
    path = _resolve_template_path(template_id)
    image = thumbnails.image_path(path, n)
    if image is None:
        thumbnails.build(path)
        image = thumbnails.image_path(path, n)
    if image is None:
        raise HTTPException(404, "no preview for this slide (LibreOffice unavailable?)")
    return FileResponse(image, media_type="image/png", headers={"Cache-Control": "max-age=86400"})


@app.get("/api/templates/{template_id}/inspect")
def inspect_template(template_id: str) -> dict:
    """The parsed template plus, per slide, what generation will do with each shape.

    Powers the UI's template inspector: `roles` maps shape_id -> title / body /
    card / table / picture / chrome / display_accent / data_placeholder / text
    / decor (see `design_system.classify_shapes`), `slots` is the slide's
    `SlotSummary`, so a person can see exactly where content will land.
    """
    try:
        deck, _ = _load_template(template_id)
    except (FileNotFoundError, KeyError) as exc:
        raise HTTPException(404, f"template {template_id!r} not found") from exc
    return {
        "deck": deck.model_dump(),
        "slides": [
            {
                "index": slide.index,
                "layout_name": slide.layout_name,
                "roles": {str(k): v for k, v in classify_shapes(slide).items()},
                "slots": describe_slots(slide).model_dump(),
            }
            for slide in deck.slides
        ],
    }


@app.post("/api/templates")
def upload_template(file: UploadFile = File(...)) -> dict[str, str]:  # noqa: B008 (FastAPI's DI pattern)
    """Save an uploaded .pptx for this uploader only — never the shared library.

    Lands in `storage.UPLOADED_TEMPLATES_DIR`, not `evals/templates/`, so it
    never appears in `GET /api/templates`'s listing for anyone else; only the
    id this returns (which only the uploader's own browser ever holds) can
    load it, via `_resolve_template_path`. Validated by actually running it
    through `parse()` — a file that isn't real .pptx (wrong format, corrupted
    zip, ...) is rejected and removed rather than left on disk to break
    template selection later.
    """
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise HTTPException(400, "only .pptx files are accepted")

    storage.UPLOADED_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    stem = _sanitize_stem(file.filename)
    dest = storage.UPLOADED_TEMPLATES_DIR / f"{stem}.pptx"
    suffix = 2
    while dest.exists():
        dest = storage.UPLOADED_TEMPLATES_DIR / f"{stem}-{suffix}.pptx"
        suffix += 1

    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    try:
        parse(dest)
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"not a valid .pptx file: {exc}") from exc

    template_id = f"upload:{dest.stem}"

    # Catalogue its slides and render its previews in the background —
    # preparation, not generation.
    def prepare() -> None:
        build_catalog(dest)
        thumbnails.build(dest)

    threading.Thread(target=prepare, daemon=True).start()
    return {"id": template_id, "label": dest.stem}


@app.post("/api/templates/{template_id}/catalog")
def catalog_template(template_id: str) -> dict:
    """Catalogue an existing template's slides now (blocking; preparation step).

    Returns which slides were kept for generation and what each is for.
    """
    path = _resolve_template_path(template_id)
    build_catalog(path)
    catalog = storage.load_catalog(path)
    if catalog is None:
        raise HTTPException(502, "cataloguing failed — the template keeps layout-based selection")
    return {
        "template_id": template_id,
        "slides": [e.model_dump() for e in catalog.entries],
        "usable": sum(e.usable for e in catalog.entries),
    }


class OutlineRequest(BaseModel):
    # Empty string means "the brand pack's first template, else pick one from
    # the brief's own topic" — see `_choose_template`.
    template_id: str = ""
    # The talk request ("выступление на финале хакатона"), or a full brief
    # when no sources are attached.
    brief: str = DEMO_BRIEF
    # None = derived from `duration_minutes` (or 10 when that's missing too).
    slide_count: int | None = None
    # One of generator.outline.MODES, or None to let the model infer it from
    # the brief — see "Content modes" in skills/outline-generation/SKILL.md.
    mode: str | None = None
    # "compact" / "standard" / "detailed" — from the UI's leading question
    # when the brief doesn't say. Shapes how much generate_content writes.
    density: str | None = None
    # Prepared context: a built brand pack (`/api/brand-packs`) and the
    # talk's uploaded material (`/api/sources`). Both optional.
    brand_pack_id: str = ""
    source_id: str = ""
    # Talk length. Sets the slide count and each slide's speaker-notes budget.
    duration_minutes: float | None = None
    # Gamma-style controls. `outline`: a plan the user reviewed/edited after
    # `/api/outline` — generation then writes exactly those slides. `text_mode`:
    # generate / condense / preserve (see generator.outline.TEXT_MODES).
    # `card_split`: "input_breaks" makes each "---"-separated part of the
    # brief one slide; "auto" lets the outline split the content.
    outline: Outline | None = None
    text_mode: str = "generate"
    card_split: str = "auto"
    # False when there is no talk ("Выступления не будет"): no speaker notes
    # are written, so none show under the slides or go into the .pptx.
    speaker_notes: bool = True


class PreparedRequest(BaseModel):
    """Everything the LLM stages need, resolved from an `OutlineRequest`."""

    model_config = {"arbitrary_types_allowed": True}

    deck: Deck
    design_system: DesignSystem
    brief: str
    brand: str | None
    slide_count: int
    duration_seconds: int | None
    sections: list[str] = []
    text_mode: str = "generate"
    fact_sheet: FactSheet | None = None
    # (content type, base64) pictures from the talk's material, and their file
    # names (shown to the writer, who picks where each goes — see
    # images.apply_user_images; the rest fill empty picture frames).
    images: list[tuple[str, str]] = []
    image_names: list[str] = []
    speaker_notes: bool = True


def _pick_template_id(req: OutlineRequest) -> str:
    if req.template_id:
        return req.template_id
    if req.brand_pack_id:
        pack_templates = sorted(
            t for t in _discover_templates() if t.startswith(f"{req.brand_pack_id}:")
        )
        if pack_templates:
            return pack_templates[0]
    return _choose_template(req.brief)


def _prepare(req: OutlineRequest) -> PreparedRequest:
    """Resolve template, brand pack and timing — no LLM calls, fast."""
    deck, design_system = _load_template(_pick_template_id(req))
    brand = None
    if req.brand_pack_id:
        context = storage.load_brand(req.brand_pack_id)
        if context is None:
            raise HTTPException(
                404, f"brand pack {req.brand_pack_id!r} is missing or not built yet"
            )
        brand = context.prompt_text()
    if req.slide_count:
        slide_count = req.slide_count
    elif req.duration_minutes:
        slide_count = slide_count_for(req.duration_minutes)
    else:
        slide_count = 10
    duration_seconds = round(req.duration_minutes * 60) if req.duration_minutes else None
    sections = split_sections(req.brief) if req.card_split == "input_breaks" else []
    if sections:
        slide_count = len(sections)
    return PreparedRequest(
        sections=sections,
        text_mode=req.text_mode,
        deck=deck,
        design_system=design_system,
        brief=req.brief,
        brand=brand,
        slide_count=slide_count,
        duration_seconds=duration_seconds,
        speaker_notes=req.speaker_notes,
    )


# Raw material used as the brief when the fact-sheet call can't finish in its
# share of the budget — longer than a fact sheet, but still prompt-sized.
_RAW_SOURCE_BUDGET = 7_000


def _digest(req: OutlineRequest, prepared: PreparedRequest, deadline: float | None = None) -> None:
    """Fold the talk's source material into the brief as a fact sheet (1 LLM call).

    Cached per (sources, request): a re-run on the same material skips the
    call. If the call can't finish before `deadline`, the brief falls back to
    the raw material itself, trimmed — slower to read for the later stages
    than a fact sheet, but the generation still completes in budget.
    """
    if not req.source_id:
        return
    bundle = storage.load_sources(req.source_id)
    if bundle is None:
        raise HTTPException(404, f"unknown source_id: {req.source_id!r}")
    prepared.images = [(i.content_type, i.data_b64) for i in bundle.images]
    prepared.image_names = [i.name for i in bundle.images]
    sheet = storage.load_fact_sheet(bundle.id, req.brief)
    if sheet is None:
        try:
            sheet = digest_sources(bundle, req.brief, client=InferenceClient(deadline=deadline))
            storage.save_fact_sheet(bundle.id, req.brief, sheet)
        except QuotaExhausted:
            raise
        except (InferenceError, httpx.HTTPError):
            raw = bundle.source_text(budget=_RAW_SOURCE_BUDGET)
            prepared.brief = f"Talk request:\n{req.brief}\n\nSource material:\n{raw}"
            return
    prepared.fact_sheet = sheet
    prepared.brief = f"Talk request:\n{req.brief}\n\nFact sheet:\n{sheet.to_text()}"


def _outline(
    req: OutlineRequest, prepared: PreparedRequest, deadline: float | None = None
) -> Outline:
    return generate_outline(
        prepared.brief,
        prepared.slide_count,
        prepared.design_system.patterns,
        mode=req.mode,
        brand=prepared.brand,
        duration_seconds=prepared.duration_seconds,
        sections=prepared.sections or None,
        text_mode=req.text_mode,
        client=InferenceClient(deadline=deadline),
    )


def _plan(req: OutlineRequest, prepared: PreparedRequest, deadline: float | None) -> Outline:
    """The user's reviewed outline when given (no LLM call), else a fresh one."""
    if req.outline is not None and req.outline.slides:
        return finalize_outline(
            req.outline.model_copy(deep=True),
            prepared.design_system.patterns,
            prepared.duration_seconds,
        )
    return _outline(req, prepared, deadline)


def _write_content(
    outline: Outline,
    prepared: PreparedRequest,
    density: str | None = None,
    deadline: float | None = None,
) -> DeckContent:
    """Content generation pinned to the exact template slides composition will use.

    The composer builds each slide on a specific template slide (round-robin
    among a layout's instances); pinning that assignment first lets the writer
    be told that slide's real slot counts ("exactly 3 cards"). `density`
    (compact/standard/detailed, from the UI's leading question) shapes how
    much the writer puts in each free-form slide — see `generate_content`.
    """
    template_slides = pick_template_slides([s.role for s in outline.slides], prepared.deck)
    return generate_content(
        outline,
        prepared.design_system.patterns,
        prepared.brief,
        template_slides=template_slides,
        density=density,
        brand=prepared.brand,
        deadline=deadline,
        text_mode=prepared.text_mode,
        user_images=prepared.image_names,
        speaker_notes=prepared.speaker_notes,
        client=InferenceClient(deadline=deadline),
    )


def _inference_errors(exc: Exception) -> HTTPException:
    """Map pipeline exceptions to HTTP errors the UI can show.

    Converting (rather than letting them escape) also keeps CORSMiddleware's
    headers on the error response — an uncaught exception bypasses CORS and
    the browser reports it as a CORS failure, hiding the real cause.
    """
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, QuotaExhausted):
        return HTTPException(429, str(exc))
    if isinstance(exc, RuntimeError) and "INFERENCE_API_KEY" in str(exc):
        return HTTPException(503, str(exc))
    return HTTPException(502, f"inference call failed: {exc}")


@app.post("/api/outline")
def create_outline(req: OutlineRequest) -> Outline:
    try:
        prepared = _prepare(req)
        _digest(req, prepared)
        return _outline(req, prepared)
    except Exception as exc:
        raise _inference_errors(exc) from exc


@app.post("/api/content")
def create_content(req: OutlineRequest) -> DeckContent:
    """parse -> (digest) -> outline -> content, in one request."""
    try:
        prepared = _prepare(req)
        _digest(req, prepared)
        return _write_content(_plan(req, prepared, None), prepared, req.density)
    except Exception as exc:
        raise _inference_errors(exc) from exc


class VariantResult(BaseModel):
    deck: Deck
    findings: list[Finding]


class DeckAudit(BaseModel):
    compact: VariantResult
    standard: VariantResult
    detailed: VariantResult
    # Planned speaking seconds per slide (empty when no talk length given).
    slide_seconds: list[int] = []
    fact_sheet: FactSheet | None = None
    # Wall-clock seconds per pipeline stage, plus "total".
    timings: dict[str, float] = {}
    # Speaking time the generated notes actually take, per slide, at
    # `WORDS_PER_MINUTE` — the honest check against the requested length.
    spoken_seconds: list[int] = []


def _build_audit(variants: dict[str, Deck], template_deck: Deck, brief: str) -> DeckAudit:
    """Run the deterministic checks on each composed variant and bundle results.

    The brief (with the fact sheet, when sources were given) is passed as
    `source_text` so the audit can flag figures that appear in the deck but
    were never in the material (likely model-invented).
    """
    return DeckAudit(
        **{
            name: VariantResult(
                deck=composed,
                findings=run_checks(composed, template_deck, source_text=brief),
            )
            for name, composed in variants.items()
        }
    )


# The task statement's budget for generating from prepared context, and how
# it's shared between stages (LLM stages only; parse/layout/audit take < 1 s).
GENERATION_BUDGET_SECONDS = 300
_DIGEST_BUDGET_SECONDS = 75
_OUTLINE_BUDGET_SECONDS = 75
_CONTENT_MIN_SECONDS = 120


def _run_pipeline(req: OutlineRequest) -> Iterator[tuple[str, dict]]:
    """The full pipeline as a stream of (event, data) pairs.

    Emits `stage` events as each stage starts and finishes (with its elapsed
    seconds), then one `result` event carrying the `DeckAudit`. Exceptions
    propagate to the caller.
    """
    started = time.monotonic()
    timings: dict[str, float] = {}

    def stage(name: str, status: str) -> tuple[str, dict]:
        data: dict = {
            "stage": name,
            "status": status,
            "elapsed": round(time.monotonic() - started, 1),
        }
        return "stage", data

    def timed(name: str, fn):
        t0 = time.monotonic()
        value = fn()
        timings[name] = round(time.monotonic() - t0, 1)
        return value

    yield stage("parse", "active")
    prepared = timed("parse", lambda: _prepare(req))
    yield stage("parse", "done")

    if req.source_id:
        yield stage("digest", "active")
        timed("digest", lambda: _digest(req, prepared, started + _DIGEST_BUDGET_SECONDS))
        yield stage("digest", "done")

    yield stage("outline", "active")
    # Outline gets its own cap, and always leaves the content stage at least
    # _CONTENT_MIN_SECONDS of the budget.
    outline_deadline = min(
        time.monotonic() + _OUTLINE_BUDGET_SECONDS,
        started + GENERATION_BUDGET_SECONDS - _CONTENT_MIN_SECONDS,
    )
    outline = timed("outline", lambda: _plan(req, prepared, outline_deadline))
    yield stage("outline", "done")

    yield stage("content", "active")
    # Optional repair passes stop in time for the 5-minute budget; layout and
    # audit after content take well under a second.
    content_deadline = started + GENERATION_BUDGET_SECONDS - 10
    content = timed(
        "content", lambda: _write_content(outline, prepared, req.density, content_deadline)
    )
    yield stage("content", "done")

    yield stage("layout", "active")
    variants = timed("layout", lambda: _compose_variants(content, prepared.deck, prepared.images))
    yield stage("layout", "done")

    yield stage("audit", "active")
    result = timed("audit", lambda: _build_audit(variants, prepared.deck, prepared.brief))
    yield stage("audit", "done")

    timings["total"] = round(time.monotonic() - started, 1)
    result.slide_seconds = [s.seconds for s in outline.slides] if prepared.duration_seconds else []
    result.fact_sheet = prepared.fact_sheet
    result.timings = timings
    result.spoken_seconds = [
        round(len((s.speaker_notes or "").split()) * 60 / WORDS_PER_MINUTE) for s in content.slides
    ]
    yield "result", result.model_dump(mode="json")


@app.post("/api/audit")
def create_audit(req: OutlineRequest) -> DeckAudit:
    """parse -> digest -> outline -> content -> layout -> audit, all 3 variants."""
    try:
        for event, data in _run_pipeline(req):
            if event == "result":
                return DeckAudit.model_validate(data)
    except Exception as exc:
        raise _inference_errors(exc) from exc
    raise HTTPException(500, "pipeline ended without a result")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/api/audit/stream")
def create_audit_stream(req: OutlineRequest) -> StreamingResponse:
    """Same pipeline as `/api/audit`, streamed as Server-Sent Events.

    Each stage emits a `stage` event the moment it actually starts/finishes
    on the backend (with seconds elapsed since the request began), so the UI
    shows real progress against the 5-minute budget. Ends with either a
    `result` event (the `DeckAudit` payload) or an `error` event.
    """

    def gen() -> Iterator[str]:
        try:
            for event, data in _run_pipeline(req):
                yield _sse(event, data)
        except Exception as exc:
            yield _sse("error", {"detail": str(_inference_errors(exc).detail)})

    return StreamingResponse(gen(), media_type="text/event-stream")


class DeckVariants(BaseModel):
    compact: Deck
    standard: Deck
    detailed: Deck


@app.post("/api/layout")
def create_layout(req: OutlineRequest) -> DeckVariants:
    """parse -> digest -> outline -> content -> compose, all 3 density variants."""
    try:
        prepared = _prepare(req)
        _digest(req, prepared)
        content = _write_content(_plan(req, prepared, None), prepared, req.density)
        return DeckVariants(**_compose_variants(content, prepared.deck, prepared.images))
    except Exception as exc:
        raise _inference_errors(exc) from exc


def _template_for(deck: Deck) -> Path | None:
    """The deck's template, only if it is one we know about.

    `source_path` arrives from the client, and an arbitrary path must never
    be opened.
    """
    if not deck.source_path:
        return None
    uploaded = (
        storage.UPLOADED_TEMPLATES_DIR.glob("*.pptx")
        if storage.UPLOADED_TEMPLATES_DIR.is_dir()
        else []
    )
    known = {str(p.resolve()): p for p in (*_discover_templates().values(), *uploaded)}
    return known.get(str(Path(deck.source_path).resolve()))


# Rendered pages by deck content: a variant switch back and forth, a
# re-opened chat, or a deep audit right after looking at the preview,
# doesn't pay for LibreOffice again. Shared by /api/preview and
# /api/audit/deep — both need "this deck's slides as images", just for
# different purposes.
_PAGE_CACHE: dict[str, list[bytes]] = {}
_PAGE_CACHE_SIZE = 24


def _rendered_pages(deck: Deck) -> list[bytes]:
    """PNG bytes per slide of `deck`, in slide order. Raises `RenderUnavailable`."""
    key = hashlib.sha256(deck.model_dump_json().encode()).hexdigest()
    cached = _PAGE_CACHE.get(key)
    if cached is not None:
        return cached
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "deck.pptx"
        export_pptx(deck, out, template_path=_template_for(deck))
        pages = render_pptx(out)
    if len(_PAGE_CACHE) >= _PAGE_CACHE_SIZE:
        _PAGE_CACHE.pop(next(iter(_PAGE_CACHE)))
    _PAGE_CACHE[key] = pages
    return pages


class DeckPreview(BaseModel):
    # One PNG per slide, as data: URLs, in deck order.
    slides: list[str]


@app.post("/api/preview")
def preview_deck(deck: Deck) -> DeckPreview:
    """The exported .pptx itself, rendered to images — what the user downloads.

    501 when LibreOffice isn't installed; the UI then keeps its own drawing.
    """
    try:
        pages = _rendered_pages(deck)
    except RenderUnavailable as exc:
        raise HTTPException(501, str(exc)) from exc
    slides = ["data:image/png;base64," + base64.b64encode(p).decode("ascii") for p in pages]
    return DeckPreview(slides=slides)


_MAX_SLIDE_IMAGE_CHARS = 8_000_000  # one data: URL, ~6 MB of PNG


class DeepAuditRequest(BaseModel):
    deck: Deck
    # The brief the deck was generated from — grounds the fact-traceability
    # check and gives the VLM the same source of truth generation itself used.
    brief: str = ""
    # One `data:image/...` URL per slide, in deck order, drawn by the browser
    # from the very .pptx the user downloads. With them the check needs no
    # server-side renderer; without, the server tries LibreOffice.
    images: list[str] | None = None


class DeepAuditResult(BaseModel):
    findings: list[Finding]


@app.post("/api/audit/deep")
def deep_audit(req: DeepAuditRequest) -> DeepAuditResult:
    """AUDIT.md's §Модельные: a VLM judges each rendered slide against ten checks.

    Not part of the 5-minute generation budget or the always-on deterministic
    pass in /api/audit — an explicit, on-demand deep pass over a deck the
    user is already looking at, one LLM call per slide. Slide images come from
    the browser (`images`) when it sends them; otherwise they are rendered
    here, which needs LibreOffice — 501 without it, like /api/preview.
    """
    if req.images is not None:
        if len(req.images) != len(req.deck.slides):
            raise HTTPException(400, "images must be one per slide, in deck order")
        if any(
            not i.startswith("data:image/") or len(i) > _MAX_SLIDE_IMAGE_CHARS for i in req.images
        ):
            raise HTTPException(400, "each image must be a data:image/... URL under ~6 MB")
        images = {slide.index: url for slide, url in zip(req.deck.slides, req.images, strict=True)}
    else:
        try:
            pages = _rendered_pages(req.deck)
        except RenderUnavailable as exc:
            raise HTTPException(501, str(exc)) from exc
        images = {
            slide.index: "data:image/png;base64," + base64.b64encode(page).decode("ascii")
            for slide, page in zip(req.deck.slides, pages, strict=False)
        }
    try:
        findings = run_model_checks(req.deck, req.brief, images)
    except Exception as exc:
        raise _inference_errors(exc) from exc
    return DeepAuditResult(findings=findings)


@app.post("/api/export")
def export_deck(deck: Deck) -> Response:
    """Composed deck IR -> a native, editable .pptx with speaker notes.

    Built from the template file itself when the deck names a known template,
    so the template's backgrounds, masters and artwork carry over.
    """
    template = _template_for(deck)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "deck.pptx"
        export_pptx(deck, out, template_path=template)
        data = out.read_bytes()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": 'attachment; filename="deck.pptx"'},
    )
