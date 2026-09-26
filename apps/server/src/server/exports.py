import base64
import hashlib
import tempfile
from pathlib import Path

from export.export import export_pptx
from export.render import RenderUnavailable, render_pptx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from ir_schema import Deck
from pydantic import BaseModel

from server.templates import _discover_templates

router = APIRouter()


def _template_for(deck: Deck) -> Path | None:
    """The deck's template, only if it is one we know about.

    `source_path` arrives from the client, and an arbitrary path must never
    be opened.
    """
    if not deck.source_path:
        return None
    known = {str(p.resolve()): p for p in _discover_templates().values()}
    return known.get(str(Path(deck.source_path).resolve()))


# Rendered previews by deck content: a variant switch back and forth, or a
# re-opened chat, doesn't pay for LibreOffice again.
_PREVIEW_CACHE: dict[str, list[str]] = {}
_PREVIEW_CACHE_SIZE = 24


class DeckPreview(BaseModel):
    # One PNG per slide, as data: URLs, in deck order.
    slides: list[str]


@router.post("/api/preview")
def preview_deck(deck: Deck) -> DeckPreview:
    """The exported .pptx itself, rendered to images — what the user downloads.

    501 when LibreOffice isn't installed; the UI then keeps its own drawing.
    """
    key = hashlib.sha256(deck.model_dump_json().encode()).hexdigest()
    cached = _PREVIEW_CACHE.get(key)
    if cached is not None:
        return DeckPreview(slides=cached)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "deck.pptx"
        export_pptx(deck, out, template_path=_template_for(deck))
        try:
            pages = render_pptx(out)
        except RenderUnavailable as exc:
            raise HTTPException(501, str(exc)) from exc
    slides = ["data:image/png;base64," + base64.b64encode(p).decode("ascii") for p in pages]
    if len(_PREVIEW_CACHE) >= _PREVIEW_CACHE_SIZE:
        _PREVIEW_CACHE.pop(next(iter(_PREVIEW_CACHE)))
    _PREVIEW_CACHE[key] = slides
    return DeckPreview(slides=slides)


@router.post("/api/export")
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
