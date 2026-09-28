"""Template preview images for the template picker.

The picker shows each template as a real rendered slide (and a few more in
its preview pane), plus light/dark/colourful/business filters; the template
inspector shows every slide as rendered, with the generation slots drawn over
it. Rendering a template means a LibreOffice run (seconds), so it's done once
per template file — keyed by content hash like the slide catalog — in the
background at start-up and after an upload, and served from disk afterwards.

data/thumbnails/<sha256>-v<N>/meta.json          {"slides": [...], "tags": [...], "pages": count}
data/thumbnails/<sha256>-v<N>/<n>.png            n-th picker preview (0 = cover)
data/thumbnails/<sha256>-v<N>/slide-<index>.jpg  template slide <index>, full size
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import threading
from pathlib import Path

from export.render import RenderUnavailable, render_pptx

from server import storage

THUMBS_DIR = storage.DATA_DIR / "thumbnails"
# Cover plus a few content slides — enough for the preview pane's stack.
PREVIEW_SLIDES = 4
RENDER_WIDTH_PX = 640
# Every slide for the inspector; JPEG keeps ~50 photo-heavy templates small.
SLIDE_WIDTH_PX = 1280
SLIDE_JPEG_QUALITY = 85

_BUSINESS = re.compile(
    r"business|consult|corporate|pitch|market|report|plan|proposal|sales|strateg|mckinsey"
    r"|law|invest|finance|agenda|meeting|roadmap|portfolio|analysis|research",
    re.IGNORECASE,
)
_lock = threading.Lock()


# Bump when rendering changes so old previews are redrawn
# (2: rendered in the template's own fonts, see export.fonts;
#  3: every slide kept full size for the inspector).
RENDER_VERSION = 3


def _dir(template: Path) -> Path:
    digest = hashlib.sha256(template.read_bytes()).hexdigest()[:24]
    return THUMBS_DIR / f"{digest}-v{RENDER_VERSION}"


def load_meta(template: Path) -> dict | None:
    path = _dir(template) / "meta.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def image_path(template: Path, n: int) -> Path | None:
    path = _dir(template) / f"{n}.png"
    return path if path.is_file() else None


def slide_path(template: Path, index: int) -> Path | None:
    """Template slide `index` as rendered (full size), if it has been."""
    path = _dir(template) / f"slide-{index}.jpg"
    return path if path.is_file() else None


def _tags(name: str, cover_png: bytes) -> list[str]:
    """Picker filters from the rendered cover: dark/light, colourful, business."""
    from PIL import Image

    image = Image.open(io.BytesIO(cover_png)).convert("RGB").resize((64, 36))
    pixels = list(image.getdata())
    luminance = sum(0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in pixels) / len(pixels) / 255
    saturation = sum(
        (max(p) - min(p)) / max(p) if max(p) else 0 for p in pixels
    ) / len(pixels)
    tags = ["dark" if luminance < 0.45 else "light"]
    if saturation > 0.35:
        tags.append("colorful")
    if _BUSINESS.search(name):
        tags.append("business")
    return tags


def _jpeg(png: bytes) -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.open(io.BytesIO(png)).convert("RGB").save(
        out, format="JPEG", quality=SLIDE_JPEG_QUALITY, optimize=True
    )
    return out.getvalue()


def _downscaled(png: bytes, width: int) -> bytes:
    from PIL import Image

    image = Image.open(io.BytesIO(png))
    image = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def build(template: Path) -> dict | None:
    """Render and cache `template`'s preview images once; the cached meta afterwards."""
    with _lock:
        meta = load_meta(template)
        if meta is not None:
            return meta
        try:
            pages = render_pptx(template, width_px=SLIDE_WIDTH_PX)
        except RenderUnavailable:
            return None
        if not pages:
            return None
        catalog = storage.load_catalog(template)
        usable = (
            [e.index for e in catalog.entries if e.usable] if catalog else list(range(len(pages)))
        )
        # The template's own first slide is its cover even when the catalogue
        # set it aside; then the first usable content slides.
        picked = [0] + [i for i in usable if i != 0 and i < len(pages)][: PREVIEW_SLIDES - 1]
        out = _dir(template)
        out.mkdir(parents=True, exist_ok=True)
        for index, page in enumerate(pages):
            (out / f"slide-{index}.jpg").write_bytes(_jpeg(page))
        for n, index in enumerate(picked):
            (out / f"{n}.png").write_bytes(_downscaled(pages[index], RENDER_WIDTH_PX))
        meta = {"slides": picked, "tags": _tags(template.stem, pages[0]), "pages": len(pages)}
        (out / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        return meta


def build_all_in_background(templates: list[Path]) -> None:
    """Render every template still missing previews, one at a time, off-thread."""

    def run() -> None:
        for template in templates:
            try:
                if template.is_file() and load_meta(template) is None:
                    build(template)
            except Exception:
                continue

    threading.Thread(target=run, daemon=True).start()
