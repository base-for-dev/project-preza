import json
import re
import shutil
from collections.abc import Iterator
from pathlib import Path

from audit import Finding, run_checks
from design_system import DesignSystem, extract_design_system, pick_template_slides
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from generator.content import DeckContent, generate_content
from generator.outline import Outline, generate_outline
from ir_schema import Deck
from layout import compose_deck
from parser.parser import parse
from pydantic import BaseModel

app = FastAPI(title="project-preza server")

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


def _discover_templates() -> dict[str, str]:
    """id -> filename for every .pptx in evals/templates/.

    Includes both the sample templates that ship there (gitignored — each
    dev drops their own copies per evals/README.md) and anything uploaded
    via `POST /api/templates`. Scanned per-call rather than cached so a new
    file doesn't need a server restart to show up. The id is just the
    filename stem, so it's stable across a machine but not guaranteed
    unique in theory (two differently-cased or differently-extensioned
    files colliding) — acceptable for dev sample data.
    """
    return {path.stem: path.name for path in sorted(TEST_TEMPLATES_DIR.glob("*.pptx"))}


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
    filename = templates.get(template_id)
    if filename is None:
        raise HTTPException(
            404, f"unknown template_id: {template_id!r} — available: {sorted(templates)}"
        )
    path = TEST_TEMPLATES_DIR / filename
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
    """Parsed `Deck` + its `DesignSystem`, memoized per template file version."""
    path = _resolve_template_path(template_id)
    key = (str(path), path.stat().st_mtime_ns)
    cached = _DECK_CACHE.get(key)
    if cached is None:
        deck = parse(path)
        cached = (deck, extract_design_system(deck))
        _DECK_CACHE[key] = cached
    return cached


def _write_content(
    outline: Outline, deck: Deck, design_system: DesignSystem, brief: str
) -> DeckContent:
    """Content generation pinned to the exact template slides composition will use.

    The composer builds each slide on a specific template slide (round-robin
    among a layout's instances); pinning that assignment first lets the writer
    be told that slide's real slot counts ("exactly 3 cards").
    """
    template_slides = pick_template_slides([s.role for s in outline.slides], deck)
    return generate_content(
        outline, design_system.patterns, brief, template_slides=template_slides
    )


DEMO_BRIEF = (
    "A 3-day engineering offsite to fix Q4 delivery velocity. Audience: "
    "engineering leadership deciding whether to approve the budget. Argue "
    "that misalignment and technical debt are costing more than the offsite "
    "would, and lay out what the three days actually produce."
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/templates")
def list_templates() -> dict[str, list[dict[str, str]]]:
    return {"templates": [{"id": key, "label": key} for key in sorted(_discover_templates())]}


@app.post("/api/templates")
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

    return {"id": dest.stem, "label": dest.stem}


class OutlineRequest(BaseModel):
    template_id: str = "portrait-regiona"
    brief: str = DEMO_BRIEF
    slide_count: int = 10


@app.post("/api/outline")
def create_outline(req: OutlineRequest) -> Outline:
    deck, design_system = _load_template(req.template_id)

    try:
        return generate_outline(req.brief, req.slide_count, design_system.patterns)
    except RuntimeError as exc:
        # INFERENCE_API_KEY missing — surface it to the UI instead of a 500.
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        # Any other inference failure (timeout, malformed provider response, ...):
        # convert to HTTPException so CORSMiddleware still attaches headers to
        # the error response — an uncaught exception here bypasses CORS and
        # the browser reports it as a CORS failure, hiding the real cause.
        raise HTTPException(502, f"inference call failed: {exc}") from exc


@app.post("/api/content")
def create_content(req: OutlineRequest) -> DeckContent:
    """parse -> design_system -> outline -> content, in one request.

    Same request body as `/api/outline` (reused, not a new model) — this
    endpoint just carries the pipeline one stage further. `/api/outline`
    stays as-is for callers that only need the outline.
    """
    deck, design_system = _load_template(req.template_id)

    try:
        outline = generate_outline(req.brief, req.slide_count, design_system.patterns)
        return _write_content(outline, deck, design_system, req.brief)
    except RuntimeError as exc:
        # INFERENCE_API_KEY missing — surface it to the UI instead of a 500.
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        # Any other inference failure (timeout, malformed provider response, ...):
        # convert to HTTPException so CORSMiddleware still attaches headers to
        # the error response — an uncaught exception here bypasses CORS and
        # the browser reports it as a CORS failure, hiding the real cause.
        raise HTTPException(502, f"inference call failed: {exc}") from exc


class VariantResult(BaseModel):
    deck: Deck
    findings: list[Finding]


class DeckAudit(BaseModel):
    compact: VariantResult
    standard: VariantResult
    detailed: VariantResult


def _build_audit(variants: dict[str, Deck], template_deck: Deck, brief: str) -> "DeckAudit":
    """Run the deterministic checks on each composed variant and bundle results.

    The brief is passed as `source_text` so the audit can flag figures that
    appear in the deck but were never in the brief (likely model-invented).
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


@app.post("/api/audit")
def create_audit(req: OutlineRequest) -> DeckAudit:
    """parse -> design_system -> outline -> content -> layout -> audit, all 3 variants.

    Same request body as `/api/outline`/`/api/content`/`/api/layout`. Returns
    each variant's composed `Deck` *and* its findings together — the UI needs
    both (render the slide, then annotate it), and the outline+content LLM
    calls already cost 100s+ combined, so this deliberately replaces calling
    `/api/layout` and `/api/audit` separately rather than making the client
    pay for that twice. `/api/layout` itself is left as-is for callers that
    only need the composed decks.
    """
    deck, design_system = _load_template(req.template_id)

    try:
        outline = generate_outline(req.brief, req.slide_count, design_system.patterns)
        content = _write_content(outline, deck, design_system, req.brief)
        variants = {
            "compact": compose_deck(content, deck, "compact"),
            "standard": compose_deck(content, deck, "standard"),
            "detailed": compose_deck(content, deck, "detailed"),
        }
        return _build_audit(variants, deck, req.brief)
    except RuntimeError as exc:
        # INFERENCE_API_KEY missing — surface it to the UI instead of a 500.
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        # Any other inference failure (timeout, malformed provider response, ...):
        # convert to HTTPException so CORSMiddleware still attaches headers to
        # the error response — an uncaught exception here bypasses CORS and
        # the browser reports it as a CORS failure, hiding the real cause.
        raise HTTPException(502, f"inference call failed: {exc}") from exc


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/api/audit/stream")
def create_audit_stream(req: OutlineRequest) -> StreamingResponse:
    """Same pipeline as `/api/audit`, streamed as Server-Sent Events.

    Each stage emits a `stage` event the moment it actually starts/finishes
    on the backend — unlike `/api/audit`, the client isn't guessing progress
    from a single blocking response. Ends with either a `result` event
    (the same `DeckAudit` payload `/api/audit` returns) or an `error` event.
    """

    def gen() -> Iterator[str]:
        try:
            yield _sse("stage", {"stage": "parse", "status": "active"})
            deck, design_system = _load_template(req.template_id)
            yield _sse("stage", {"stage": "parse", "status": "done"})

            yield _sse("stage", {"stage": "outline", "status": "active"})
            outline = generate_outline(req.brief, req.slide_count, design_system.patterns)
            yield _sse("stage", {"stage": "outline", "status": "done"})

            yield _sse("stage", {"stage": "content", "status": "active"})
            content = _write_content(outline, deck, design_system, req.brief)
            yield _sse("stage", {"stage": "content", "status": "done"})

            yield _sse("stage", {"stage": "layout", "status": "active"})
            variants = {
                "compact": compose_deck(content, deck, "compact"),
                "standard": compose_deck(content, deck, "standard"),
                "detailed": compose_deck(content, deck, "detailed"),
            }
            yield _sse("stage", {"stage": "layout", "status": "done"})

            yield _sse("stage", {"stage": "audit", "status": "active"})
            result = _build_audit(variants, deck, req.brief)
            yield _sse("stage", {"stage": "audit", "status": "done"})
            yield _sse("result", result.model_dump(mode="json"))
        except HTTPException as exc:
            yield _sse("error", {"detail": str(exc.detail)})
        except RuntimeError as exc:
            # INFERENCE_API_KEY missing.
            yield _sse("error", {"detail": str(exc)})
        except Exception as exc:
            yield _sse("error", {"detail": f"inference call failed: {exc}"})

    return StreamingResponse(gen(), media_type="text/event-stream")


class DeckVariants(BaseModel):
    compact: Deck
    standard: Deck
    detailed: Deck


@app.post("/api/layout")
def create_layout(req: OutlineRequest) -> DeckVariants:
    """parse -> design_system -> outline -> content -> compose, all 3 density variants.

    Runs the LLM stages (outline, content) exactly once, then calls
    `compose_deck` three times (compact/standard/detailed) with zero extra
    LLM calls — per PRODUCT.md, the UI wants all 3 variants side by side.
    Same request body as `/api/outline`/`/api/content`.
    """
    deck, design_system = _load_template(req.template_id)

    try:
        outline = generate_outline(req.brief, req.slide_count, design_system.patterns)
        content = _write_content(outline, deck, design_system, req.brief)
        return DeckVariants(
            compact=compose_deck(content, deck, "compact"),
            standard=compose_deck(content, deck, "standard"),
            detailed=compose_deck(content, deck, "detailed"),
        )
    except RuntimeError as exc:
        # INFERENCE_API_KEY missing — surface it to the UI instead of a 500.
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        # Any other inference failure (timeout, malformed provider response, ...):
        # convert to HTTPException so CORSMiddleware still attaches headers to
        # the error response — an uncaught exception here bypasses CORS and
        # the browser reports it as a CORS failure, hiding the real cause.
        raise HTTPException(502, f"inference call failed: {exc}") from exc
