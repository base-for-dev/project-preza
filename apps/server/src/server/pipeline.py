import json
import time
from collections.abc import Iterator

from audit import Finding, run_checks
from design_system import (
    DesignSystem,
    pick_template_slides,
)
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from generator.content import DeckContent, generate_content
from generator.outline import Outline, generate_outline
from generator.timing import WORDS_PER_MINUTE, slide_count_for
from images import UnsplashClient, apply_photos, find_slide_photos
from ingest import FactSheet, digest_sources
from ir_schema import Deck
from layout import compose_deck
from pydantic import BaseModel

from server import storage
from server.templates import _choose_template, _discover_templates, _load_template

router = APIRouter()

# One client for the process: cheap to construct (just reads env), and
# reusing it means the "no UNSPLASH_ACCESS_KEY configured" check happens
# once per request rather than re-reading settings on every variant.
_UNSPLASH_CLIENT = UnsplashClient()


def _compose_variants(content: DeckContent, deck: Deck) -> dict[str, Deck]:
    """All 3 density variants, with real on-topic photos swapped in where asked.

    Composition itself (`compose_deck`) never makes a network call — image
    search is a separate, best-effort step layered on top: with no Unsplash
    API key configured it's skipped and every variant keeps the template's
    own original images exactly as before. Photos are searched once and
    shared by all three variants — they differ only in text, not in slides
    or picture frames — so one generation costs one search per slide, not
    three.
    """
    variants = {
        "compact": compose_deck(content, deck, "compact"),
        "standard": compose_deck(content, deck, "standard"),
        "detailed": compose_deck(content, deck, "detailed"),
    }
    if not _UNSPLASH_CLIENT.configured:
        return variants
    photos = find_slide_photos(variants["standard"], content, _UNSPLASH_CLIENT)
    return {name: apply_photos(variant, photos) for name, variant in variants.items()}


DEMO_BRIEF = (
    "A 3-day engineering offsite to fix Q4 delivery velocity. Audience: "
    "engineering leadership deciding whether to approve the budget. Argue "
    "that misalignment and technical debt are costing more than the offsite "
    "would, and lay out what the three days actually produce."
)


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


class PreparedRequest(BaseModel):
    """Everything the LLM stages need, resolved from an `OutlineRequest`."""

    model_config = {"arbitrary_types_allowed": True}

    deck: Deck
    design_system: DesignSystem
    brief: str
    brand: str | None
    slide_count: int
    duration_seconds: int | None
    fact_sheet: FactSheet | None = None


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
    return PreparedRequest(
        deck=deck,
        design_system=design_system,
        brief=req.brief,
        brand=brand,
        slide_count=slide_count,
        duration_seconds=duration_seconds,
    )


def _digest(req: OutlineRequest, prepared: PreparedRequest) -> None:
    """Fold the talk's source material into the brief as a fact sheet (1 LLM call)."""
    if not req.source_id:
        return
    bundle = storage.load_sources(req.source_id)
    if bundle is None:
        raise HTTPException(404, f"unknown source_id: {req.source_id!r}")
    sheet = digest_sources(bundle, req.brief)
    prepared.fact_sheet = sheet
    prepared.brief = f"Talk request:\n{req.brief}\n\nFact sheet:\n{sheet.to_text()}"


def _outline(req: OutlineRequest, prepared: PreparedRequest) -> Outline:
    return generate_outline(
        prepared.brief,
        prepared.slide_count,
        prepared.design_system.patterns,
        mode=req.mode,
        brand=prepared.brand,
        duration_seconds=prepared.duration_seconds,
    )


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
    )


def _inference_errors(exc: Exception) -> HTTPException:
    """Map pipeline exceptions to HTTP errors the UI can show.

    Converting (rather than letting them escape) also keeps CORSMiddleware's
    headers on the error response — an uncaught exception bypasses CORS and
    the browser reports it as a CORS failure, hiding the real cause.
    """
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, RuntimeError) and "INFERENCE_API_KEY" in str(exc):
        return HTTPException(503, str(exc))
    return HTTPException(502, f"inference call failed: {exc}")


@router.post("/api/outline")
def create_outline(req: OutlineRequest) -> Outline:
    try:
        prepared = _prepare(req)
        _digest(req, prepared)
        return _outline(req, prepared)
    except Exception as exc:
        raise _inference_errors(exc) from exc


@router.post("/api/content")
def create_content(req: OutlineRequest) -> DeckContent:
    """parse -> (digest) -> outline -> content, in one request."""
    try:
        prepared = _prepare(req)
        _digest(req, prepared)
        return _write_content(_outline(req, prepared), prepared, req.density)
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


# The task statement's budget for generating from prepared context.
GENERATION_BUDGET_SECONDS = 300


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
        timed("digest", lambda: _digest(req, prepared))
        yield stage("digest", "done")

    yield stage("outline", "active")
    outline = timed("outline", lambda: _outline(req, prepared))
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
    variants = timed("layout", lambda: _compose_variants(content, prepared.deck))
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


@router.post("/api/audit")
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


@router.post("/api/audit/stream")
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


@router.post("/api/layout")
def create_layout(req: OutlineRequest) -> DeckVariants:
    """parse -> digest -> outline -> content -> compose, all 3 density variants."""
    try:
        prepared = _prepare(req)
        _digest(req, prepared)
        content = _write_content(_outline(req, prepared), prepared, req.density)
        return DeckVariants(**_compose_variants(content, prepared.deck))
    except Exception as exc:
        raise _inference_errors(exc) from exc
