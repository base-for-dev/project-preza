from pathlib import Path

from audit import Finding, run_checks
from design_system import extract_design_system
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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

# No template upload yet, so the UI can only offer whatever sample templates
# ship in evals/templates/ (gitignored — each dev drops their own copies
# there per evals/README.md). Real template upload is next.
TEST_TEMPLATES = {
    "portrait-regiona": "portrait-regiona.pptx",
}

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
    available = [
        {"id": key, "label": key}
        for key, filename in TEST_TEMPLATES.items()
        if (TEST_TEMPLATES_DIR / filename).exists()
    ]
    return {"templates": available}


class OutlineRequest(BaseModel):
    template_id: str = "portrait-regiona"
    brief: str = DEMO_BRIEF
    slide_count: int = 10


@app.post("/api/outline")
def create_outline(req: OutlineRequest) -> Outline:
    filename = TEST_TEMPLATES.get(req.template_id)
    if filename is None:
        raise HTTPException(404, f"unknown template_id: {req.template_id}")

    path = TEST_TEMPLATES_DIR / filename
    if not path.exists():
        raise HTTPException(
            404,
            f"template file missing on disk: {path.relative_to(REPO_ROOT)} "
            "— see evals/README.md to fetch sample templates locally",
        )

    deck = parse(path)
    design_system = extract_design_system(deck)

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
    filename = TEST_TEMPLATES.get(req.template_id)
    if filename is None:
        raise HTTPException(404, f"unknown template_id: {req.template_id}")

    path = TEST_TEMPLATES_DIR / filename
    if not path.exists():
        raise HTTPException(
            404,
            f"template file missing on disk: {path.relative_to(REPO_ROOT)} "
            "— see evals/README.md to fetch sample templates locally",
        )

    deck = parse(path)
    design_system = extract_design_system(deck)

    try:
        outline = generate_outline(req.brief, req.slide_count, design_system.patterns)
        return generate_content(outline, design_system.patterns, req.brief)
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
    filename = TEST_TEMPLATES.get(req.template_id)
    if filename is None:
        raise HTTPException(404, f"unknown template_id: {req.template_id}")

    path = TEST_TEMPLATES_DIR / filename
    if not path.exists():
        raise HTTPException(
            404,
            f"template file missing on disk: {path.relative_to(REPO_ROOT)} "
            "— see evals/README.md to fetch sample templates locally",
        )

    deck = parse(path)
    design_system = extract_design_system(deck)

    try:
        outline = generate_outline(req.brief, req.slide_count, design_system.patterns)
        content = generate_content(outline, design_system.patterns, req.brief)
        variants = {
            "compact": compose_deck(content, deck, "compact"),
            "standard": compose_deck(content, deck, "standard"),
            "detailed": compose_deck(content, deck, "detailed"),
        }
        return DeckAudit(
            compact=VariantResult(
                deck=variants["compact"], findings=run_checks(variants["compact"], deck)
            ),
            standard=VariantResult(
                deck=variants["standard"], findings=run_checks(variants["standard"], deck)
            ),
            detailed=VariantResult(
                deck=variants["detailed"], findings=run_checks(variants["detailed"], deck)
            ),
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
    filename = TEST_TEMPLATES.get(req.template_id)
    if filename is None:
        raise HTTPException(404, f"unknown template_id: {req.template_id}")

    path = TEST_TEMPLATES_DIR / filename
    if not path.exists():
        raise HTTPException(
            404,
            f"template file missing on disk: {path.relative_to(REPO_ROOT)} "
            "— see evals/README.md to fetch sample templates locally",
        )

    deck = parse(path)
    design_system = extract_design_system(deck)

    try:
        outline = generate_outline(req.brief, req.slide_count, design_system.patterns)
        content = generate_content(outline, design_system.patterns, req.brief)
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
