import re
import shutil
import threading
from pathlib import Path

from design_system import (
    DesignSystem,
    apply_catalog,
    classify_shapes,
    describe_slots,
    extract_design_system,
)
from fastapi import APIRouter, File, HTTPException, UploadFile
from ir_schema import Deck
from parser.parser import parse

from server import storage
from server.context_api import build_catalog

router = APIRouter()

REPO_ROOT = Path(__file__).resolve().parents[4]
TEST_TEMPLATES_DIR = REPO_ROOT / "evals" / "templates"


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


def _resolve_template_path(template_id: str) -> Path:
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
        deck = parse(path)
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
        keywords = _TEMPLATE_TOPIC_HINTS.get(template_id) or [
            w
            for w in re.split(r"[-_\s]+", template_id.lower())
            if w and w not in _GENERIC_FILENAME_WORDS and len(w) >= 3
        ]
        score = sum(1 for kw in keywords if kw and kw in text)
        if score > best_score:
            best_id, best_score = template_id, score
    return best_id


@router.get("/api/templates")
def list_templates() -> dict[str, list[dict[str, str]]]:
    # Brand-pack templates ("<pack>:<stem>") show just their file name.
    return {
        "templates": [
            {"id": key, "label": key.split(":", 1)[-1]} for key in sorted(_discover_templates())
        ]
    }


@router.get("/api/templates/{template_id}/inspect")
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


@router.post("/api/templates")
def upload_template(file: UploadFile = File(...)) -> dict[str, str]:  # noqa: B008 (FastAPI's DI pattern)
    """Save an uploaded .pptx into evals/templates/ so it shows up in `/api/templates`.

    Validated by actually running it through `parse()` — a file that isn't
    real .pptx (wrong format, corrupted zip, ...) is rejected and removed
    rather than left on disk to break template selection later.
    """
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise HTTPException(400, "only .pptx files are accepted")

    TEST_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    stem = _sanitize_stem(file.filename)
    dest = TEST_TEMPLATES_DIR / f"{stem}.pptx"
    suffix = 2
    while dest.exists():
        dest = TEST_TEMPLATES_DIR / f"{stem}-{suffix}.pptx"
        suffix += 1

    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    try:
        parse(dest)
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"not a valid .pptx file: {exc}") from exc

    # Catalogue its slides in the background — preparation, not generation.
    threading.Thread(target=build_catalog, args=(dest,), daemon=True).start()
    return {"id": dest.stem, "label": dest.stem}


@router.post("/api/templates/{template_id}/catalog")
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
