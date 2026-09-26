import tempfile
from pathlib import Path

from export.export import export_pptx
from fastapi import APIRouter
from fastapi.responses import Response
from ir_schema import Deck

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
