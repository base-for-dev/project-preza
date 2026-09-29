""".pptx -> one PNG per slide, rendered by LibreOffice.

The web preview used to draw slides from the IR in the browser, which can't
show what the IR doesn't model — backgrounds, master artwork, theme colours,
grouped shapes, charts — so it looked nothing like the exported file. This
renders the *exported file itself*: the preview is then exactly what the user
downloads, in the template's own fonts (see export.fonts).

LibreOffice converts to PDF headless; `pypdfium2` rasterizes the pages.
One persistent LibreOffice profile is reused (a fresh profile per call adds
first-run setup to every render), and renders are serialized, since two
soffice processes can't share a profile. A render takes a few seconds,
mostly LibreOffice start-up.
"""

from __future__ import annotations

import io
import logging
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from export.fonts import with_fonts

log = logging.getLogger(__name__)

_CANDIDATES = (
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/bin/libreoffice",
    "/usr/local/bin/soffice",
    "/opt/homebrew/bin/soffice",
)
RENDER_TIMEOUT_SECONDS = 120
_PROFILE_DIR = Path(tempfile.gettempdir()) / "preza-soffice-profile"
_LOCK = threading.Lock()


class RenderUnavailable(RuntimeError):
    """LibreOffice isn't installed, or the conversion failed."""


def soffice_path() -> str | None:
    """LibreOffice's `soffice`: $SOFFICE_PATH, then PATH, then usual install dirs."""
    configured = os.environ.get("SOFFICE_PATH")
    if configured and Path(configured).is_file():
        return configured
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    return next((c for c in _CANDIDATES if Path(c).is_file()), None)


def pptx_to_pdf(pptx: Path, out_dir: Path) -> Path:
    """`pptx` converted to a vector PDF (selectable text) in `out_dir`.

    Raises `RenderUnavailable` without LibreOffice or if it produces nothing.
    """
    soffice = soffice_path()
    if soffice is None:
        raise RenderUnavailable("LibreOffice is not installed (set SOFFICE_PATH)")
    profile = _PROFILE_DIR.as_uri()
    # Convert a copy carrying the template's fonts in a form LibreOffice loads
    # (see export.fonts); without them it substitutes Arial and text reflows.
    # Font trouble must never cost the conversion itself.
    source = out_dir / "in" / pptx.name
    source.parent.mkdir(parents=True, exist_ok=True)
    try:
        with_fonts(pptx, source)
    except Exception:
        log.warning("could not prepare fonts for %s; converting as is", pptx, exc_info=True)
        shutil.copyfile(pptx, source)
    try:
        with _LOCK:
            subprocess.run(
                [
                    soffice,
                    f"-env:UserInstallation={profile}",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(out_dir),
                    str(source),
                ],
                capture_output=True,
                timeout=RENDER_TIMEOUT_SECONDS,
                check=False,
            )
    except subprocess.TimeoutExpired as exc:
        raise RenderUnavailable("LibreOffice timed out converting the deck") from exc
    pdf_path = out_dir / f"{pptx.stem}.pdf"
    if not pdf_path.is_file():
        raise RenderUnavailable("LibreOffice produced no PDF")
    return pdf_path


def render_pptx(pptx: Path, *, width_px: int = 960) -> list[bytes]:
    """PNG bytes for every slide of `pptx`, `width_px` wide."""
    import pypdfium2 as pdfium

    with tempfile.TemporaryDirectory() as tmp:
        pdf = pdfium.PdfDocument(str(pptx_to_pdf(pptx, Path(tmp))))
        pages: list[bytes] = []
        try:
            for page in pdf:
                image = page.render(scale=width_px / page.get_width()).to_pil()
                buffer = io.BytesIO()
                image.save(buffer, format="PNG", optimize=True)
                pages.append(buffer.getvalue())
        finally:
            pdf.close()
        return pages
