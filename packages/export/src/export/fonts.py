"""A template's own fonts, made available to whatever renders it.

Templates (Google Slides / Slidesgo exports especially) are set in fonts this
machine doesn't have — Chakra Petch, Montserrat, Oswald, ... A renderer that
can't find them substitutes Arial, which is wider: titles wrap ("BACKGROU /
ND") and text runs over the template's plates and artwork. The template file
itself is fine — the fonts are even embedded in it — they just weren't
readable (see export.mtx).

Sources, per family and style (regular / bold / italic / boldItalic):
  1. the template's embedded fonts, decoded from EOT/MTX — exactly the
     designer's files, and complete (not subset);
  2. Google Fonts, for families or styles the template didn't embed — almost
     every free template font is a Google font. Fetched once, cached on disk.
Anything else (system fonts, proprietary fonts that weren't embedded) is left
to the renderer's own substitution.

The fonts reach LibreOffice as uncompressed EOT inside a *copy* of the deck
(`with_fonts`) — the only way it loads fonts per document, and the one EOT
flavour its libeot reads. The downloaded deck is never touched: PowerPoint
reads the original embedded fonts itself. The browser gets the same TTFs
from the cache via `font_file`/`font_css`.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import shutil
import struct
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from fontTools.ttLib import TTFont

from export.mtx import eot_to_ttf

log = logging.getLogger(__name__)

# Where decoded/downloaded fonts live: <CACHE_DIR>/<family>/<style>.ttf.
# The server points this at its data directory.
CACHE_DIR = Path.home() / ".cache" / "preza" / "fonts"

STYLES = ("regular", "bold", "italic", "boldItalic")
_STYLE_NAMES = {
    "regular": "Regular",
    "bold": "Bold",
    "italic": "Italic",
    "boldItalic": "Bold Italic",
}

# Fonts every renderer here already has (macOS system fonts, or bundled with
# LibreOffice — it maps Calibri/Cambria to its metric-compatible Carlito/
# Caladea itself). Not worth a network lookup.
_KNOWN_LOCAL = {
    "arial",
    "arial black",
    "arial narrow",
    "arial unicode ms",
    "helvetica",
    "helvetica neue",
    "times",
    "times new roman",
    "courier",
    "courier new",
    "georgia",
    "verdana",
    "tahoma",
    "trebuchet ms",
    "impact",
    "comic sans ms",
    "palatino",
    "palatino linotype",
    "gill sans",
    "futura",
    "optima",
    "didot",
    "menlo",
    "monaco",
    "avenir",
    "avenir next",
    "baskerville",
    "symbol",
    "wingdings",
    "webdings",
    "calibri",
    "calibri light",
    "cambria",
    "cambria math",
    "aptos",
    "segoe ui",
    "consolas",
    "candara",
    "constantia",
    "corbel",
    "franklin gothic",
    "century gothic",
    "garamond",
    "book antiqua",
    "lucida grande",
    "lucida sans",
    "dejavu sans",
    "liberation sans",
    "liberation serif",
    "noto sans",
    "noto serif",
    "carlito",
    "caladea",
    "open symbol",
    "opensymbol",
}

# Google Slides names weights as their own families ("Montserrat SemiBold").
_WEIGHT_WORDS = {
    "thin": 100,
    "hairline": 100,
    "extralight": 200,
    "ultralight": 200,
    "light": 300,
    "regular": 400,
    "normal": 400,
    "book": 400,
    "medium": 500,
    "semibold": 600,
    "demibold": 600,
    "bold": 700,
    "extrabold": 800,
    "ultrabold": 800,
    "black": 900,
    "heavy": 900,
}

_GOOGLE_CSS = "https://fonts.googleapis.com/css"
_GOOGLE_SUBSETS = "latin,latin-ext,cyrillic,cyrillic-ext"
_HTTP_TIMEOUT = 15
_MISSING = ".missing"  # marker: Google Fonts doesn't have this family

_lock = threading.Lock()

_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
_FONT_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
_FONT_CONTENT_TYPE = "application/x-fontdata"


# --- which fonts a deck uses ----------------------------------------------


def used_families(pptx: Path) -> list[str]:
    """Latin typefaces the deck's slides, layouts, masters and theme name."""
    found: set[str] = set()
    with zipfile.ZipFile(pptx) as z:
        for name in z.namelist():
            if not re.match(
                r"ppt/(slides|slideLayouts|slideMasters|theme|notesMasters)/[^/]+\.xml$", name
            ):
                continue
            xml = z.read(name).decode("utf-8", "ignore")
            found.update(re.findall(r'<a:latin\b[^>]*\btypeface="([^"]+)"', xml))
        found.update(_embedded_entries(z))
    return sorted(
        f for f in found if f and not f.startswith("+") and f.lower() not in _KNOWN_LOCAL and _safe_family(f)
    )


def _safe_family(name: str) -> bool:
    """A typeface name comes from an untrusted file and becomes a folder name in the
    cache: refuse anything that could point outside it."""
    return (
        len(name) <= 100
        and not name.startswith(".")
        and ".." not in name
        and not any(c in name for c in "/\\\0")
    )


def _embedded_entries(z: zipfile.ZipFile) -> dict[str, dict[str, str]]:
    """{typeface: {style: part name}} from presentation.xml's embeddedFontLst."""
    try:
        presentation = z.read("ppt/presentation.xml").decode("utf-8", "ignore")
        rels = z.read("ppt/_rels/presentation.xml.rels").decode("utf-8", "ignore")
    except KeyError:
        return {}
    targets = {
        m.group("id"): m.group("target")
        for m in re.finditer(
            r'<Relationship\b(?=[^>]*\bId="(?P<id>[^"]+)")(?=[^>]*\bTarget="(?P<target>[^"]+)")[^>]*>',
            rels,
        )
    }
    entries: dict[str, dict[str, str]] = {}
    for block in re.findall(r"<p:embeddedFont>(.*?)</p:embeddedFont>", presentation, re.S):
        typeface = re.search(r'<p:font\b[^>]*\btypeface="([^"]+)"', block)
        if not typeface:
            continue
        for style, rid in re.findall(
            r'<p:(regular|bold|italic|boldItalic)\b[^>]*\br:id="([^"]+)"', block
        ):
            if rid in targets:
                part = str(PurePosixPath("ppt") / targets[rid])
                entries.setdefault(typeface.group(1), {})[style] = _normalize_part(part)
    return entries


def _normalize_part(part: str) -> str:
    parts: list[str] = []
    for piece in part.split("/"):
        if piece == "..":
            parts.pop()
        elif piece and piece != ".":
            parts.append(piece)
    return "/".join(parts)


# --- sources ---------------------------------------------------------------


def _embedded_fonts(pptx: Path) -> dict[str, dict[str, bytes]]:
    """{family: {style: raw EOT bytes}} as embedded; decoded later, only on a cache miss."""
    fonts: dict[str, dict[str, bytes]] = {}
    with zipfile.ZipFile(pptx) as z:
        for family, styles in _embedded_entries(z).items():
            for style, part in styles.items():
                if part in z.namelist():
                    fonts.setdefault(family, {})[style] = z.read(part)
    return fonts


def _split_weight(family: str) -> tuple[str, int]:
    """ "Montserrat SemiBold" / "Inter-Regular" -> ("Montserrat", 600) / ("Inter", 400)."""
    words = re.split(r"[\s-]+", family.strip())
    for n in (2, 1):
        if len(words) > n:
            key = "".join(words[-n:]).lower()
            if key in _WEIGHT_WORDS:
                return " ".join(words[:-n]), _WEIGHT_WORDS[key]
    return family, 400


def _google_request(family: str, variants: dict[str, str]) -> dict[str, bytes] | None:
    """{style: ttf} for `variants` ({style: "700italic"}), or None if Google lacks the family."""
    query = urllib.parse.urlencode(
        {"family": f"{family}:{','.join(variants.values())}", "subset": _GOOGLE_SUBSETS}
    )
    try:
        with urllib.request.urlopen(f"{_GOOGLE_CSS}?{query}", timeout=_HTTP_TIMEOUT) as resp:
            css = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 400:
            return None
        raise
    faces = {}
    for block in re.findall(r"@font-face\s*{(.*?)}", css, re.S):
        style = re.search(r"font-style:\s*(\w+)", block)
        weight = re.search(r"font-weight:\s*(\d+)", block)
        url = re.search(r"url\((https://[^)]+\.ttf)\)", block)
        if style and weight and url:
            faces[f"{weight.group(1)}{'italic' if style.group(1) == 'italic' else ''}"] = url.group(
                1
            )
    fonts = {}
    for style, variant in variants.items():
        if variant in faces:
            with urllib.request.urlopen(faces[variant], timeout=_HTTP_TIMEOUT) as resp:
                fonts[style] = resp.read()
    return fonts


def _google_fonts(family: str) -> dict[str, bytes]:
    """Every style Google Fonts has for `family` (network, once; then disk)."""
    folder = CACHE_DIR / "google" / family
    if (folder / _MISSING).exists():
        return {}
    cached = {
        s: (folder / f"{s}.ttf").read_bytes() for s in STYLES if (folder / f"{s}.ttf").is_file()
    }
    if cached:
        return cached

    base, weight = family, 400
    fonts = _google_request(
        family, {"regular": "400", "bold": "700", "italic": "400italic", "boldItalic": "700italic"}
    )
    if fonts is None:
        base, weight = _split_weight(family)
        if base != family:
            bold = 700 if weight < 700 else 900
            fonts = _google_request(
                base,
                {
                    "regular": f"{weight}",
                    "bold": f"{bold}",
                    "italic": f"{weight}italic",
                    "boldItalic": f"{bold}italic",
                },
            )
    folder.mkdir(parents=True, exist_ok=True)
    if not fonts:
        (folder / _MISSING).touch()
        return {}
    for style, data in fonts.items():
        (folder / f"{style}.ttf").write_bytes(data)
    return fonts


def _prepared(source: bytes, family: str, style: str, *, is_eot: bool) -> bytes:
    """`source` (embedded EOT or a TTF) as a TTF named for the deck — cached by
    content, since decoding MTX in Python takes a while."""
    key = hashlib.sha256(source + f"\0{family}\0{style}".encode()).hexdigest()[:32]
    path = CACHE_DIR / "prepared" / f"{key}.ttf"
    if path.is_file():
        return path.read_bytes()
    data = _rename(eot_to_ttf(source) if is_eot else source, family, style)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _rename(ttf: bytes, family: str, style: str) -> bytes:
    """`ttf` named exactly `family` / `style`, as the deck refers to it.

    Font files name weights differently from decks ("Montserrat" +
    "SemiBold" vs a deck's "Montserrat SemiBold" family), and renderers match
    on the name — so every file is renamed to what the deck asks for.
    """
    font = TTFont(io.BytesIO(ttf))
    name = font["name"]
    subfamily = _STYLE_NAMES[style]
    postscript = re.sub(r"[^A-Za-z0-9]", "", family) + "-" + subfamily.replace(" ", "")
    for record_id in (16, 17, 21, 22):
        name.removeNames(nameID=record_id)
    for record_id, value in (
        (1, family),
        (2, subfamily),
        (4, f"{family} {subfamily}"),
        (6, postscript),
    ):
        name.setName(value, record_id, 3, 1, 0x409)
        name.setName(value, record_id, 1, 0, 0)
    os2 = font["OS/2"]
    bold, italic = "bold" in style.lower(), "italic" in style.lower()
    os2.fsSelection = (
        (os2.fsSelection & ~0b1100001) | (0b100000 if bold else 0) | (1 if italic else 0)
    )
    if not bold and not italic:
        os2.fsSelection |= 0b1000000  # REGULAR
    font["head"].macStyle = (1 if bold else 0) | (2 if italic else 0)
    out = io.BytesIO()
    font.save(out)
    return out.getvalue()


def template_fonts(pptx: Path) -> dict[str, dict[str, bytes]]:
    """{family: {style: ttf}} for every non-system font `pptx` uses.

    Embedded fonts win; Google Fonts fills families and styles the template
    didn't embed. Every file is also left in the cache for the browser.
    """
    with _lock:
        embedded = _embedded_fonts(pptx)
        fonts: dict[str, dict[str, bytes]] = {}
        for family in used_families(pptx):
            styles = {s: (data, True) for s, data in embedded.get(family, {}).items()}
            if len(styles) < len(STYLES):
                try:
                    google = _google_fonts(family)
                except OSError as exc:  # offline: embedded fonts still work
                    log.warning("Google Fonts lookup for %s failed: %s", family, exc)
                    google = {}
                for style, data in google.items():
                    styles.setdefault(style, (data, False))
            if not styles:
                continue
            folder = CACHE_DIR / "families" / family
            folder.mkdir(parents=True, exist_ok=True)
            fonts[family] = {}
            for style, (data, is_eot) in styles.items():
                try:
                    fonts[family][style] = _prepared(data, family, style, is_eot=is_eot)
                except Exception as exc:  # a broken font file mustn't stop the render
                    log.warning("font %s %s unusable: %s", family, style, exc)
                    continue
                (folder / f"{style}.ttf").write_bytes(fonts[family][style])
        return fonts


# --- delivery ---------------------------------------------------------------


def to_eot(ttf: bytes) -> bytes:
    """Uncompressed EOT (version 2.1) wrapping `ttf` — what LibreOffice's libeot reads."""
    font = TTFont(io.BytesIO(ttf))
    os2, head, name = font["OS/2"], font["head"], font["name"]
    p = os2.panose
    panose = bytes(
        [
            p.bFamilyType,
            p.bSerifStyle,
            p.bWeight,
            p.bProportion,
            p.bContrast,
            p.bStrokeVariation,
            p.bArmStyle,
            p.bLetterForm,
            p.bMidline,
            p.bXHeight,
        ]
    )
    body = panose + struct.pack(
        "<BBIHH", 1, 1 if os2.fsSelection & 1 else 0, os2.usWeightClass, 0, 0x504C
    )  # fsType 0: installable, so nothing refuses to use it
    body += struct.pack(
        "<IIIIII",
        os2.ulUnicodeRange1,
        os2.ulUnicodeRange2,
        os2.ulUnicodeRange3,
        os2.ulUnicodeRange4,
        getattr(os2, "ulCodePageRange1", 0),
        getattr(os2, "ulCodePageRange2", 0),
    )
    body += struct.pack("<I", head.checkSumAdjustment) + b"\0" * 16
    for record_id in (1, 2, 5, 4):  # family, style, version, full name
        record = name.getName(record_id, 3, 1, 0x409)
        value = record.toUnicode().encode("utf-16-le") if record else b""
        body += struct.pack("<HH", 0, len(value)) + value
    body += struct.pack("<HH", 0, 0)  # no RootString: usable from any document
    header_size = 16 + len(body)
    return struct.pack("<IIII", header_size + len(ttf), len(ttf), 0x00020001, 0) + body + ttf


def with_fonts(src: Path, dst: Path) -> bool:
    """Write a copy of `src` to `dst` whose embedded fonts LibreOffice can load.

    Existing embedded fonts are re-encoded in place; families/styles the deck
    didn't embed are added as new font parts. Returns False (and writes a
    plain copy) when there was nothing to add.
    """
    fonts = template_fonts(src)
    if not fonts:
        shutil.copyfile(src, dst)
        return False

    with zipfile.ZipFile(src) as zin:
        existing = _embedded_entries(zin)
        names = set(zin.namelist())
        presentation = zin.read("ppt/presentation.xml").decode("utf-8")
        rels = zin.read("ppt/_rels/presentation.xml.rels").decode("utf-8")
        content_types = zin.read("[Content_Types].xml").decode("utf-8")

        replace: dict[str, bytes] = {}
        new_fonts: dict[str, dict[str, str]] = {}  # family -> style -> rId
        rel_ids = {int(m) for m in re.findall(r'Id="rId(\d+)"', rels)}
        next_id = max(rel_ids, default=0) + 1
        new_rels = []
        for family, styles in fonts.items():
            for style, ttf in styles.items():
                eot = to_eot(ttf)
                part = existing.get(family, {}).get(style)
                if part:
                    replace[part] = eot
                    continue
                n = 1
                while (
                    f"ppt/fonts/preza-font{n}.fntdata" in names
                    or f"ppt/fonts/preza-font{n}.fntdata" in replace
                ):
                    n += 1
                part = f"ppt/fonts/preza-font{n}.fntdata"
                replace[part] = eot
                rid = f"rId{next_id}"
                next_id += 1
                new_rels.append(
                    f'<Relationship Id="{rid}" Type="{_FONT_REL}" '
                    f'Target="fonts/preza-font{n}.fntdata"/>'
                )
                new_fonts.setdefault(family, {})[style] = rid

        if new_rels:
            rels = rels.replace("</Relationships>", "".join(new_rels) + "</Relationships>")
            if 'Extension="fntdata"' not in content_types:
                content_types = content_types.replace(
                    "<Default ",
                    f'<Default Extension="fntdata" ContentType="{_FONT_CONTENT_TYPE}"/><Default ',
                    1,
                )
            presentation = _add_embedded_fonts(presentation, new_fonts)

        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                if info.filename in replace:
                    zout.writestr(info.filename, replace.pop(info.filename))
                elif info.filename == "ppt/presentation.xml":
                    zout.writestr(info, presentation)
                elif info.filename == "ppt/_rels/presentation.xml.rels":
                    zout.writestr(info, rels)
                elif info.filename == "[Content_Types].xml":
                    zout.writestr(info, content_types)
                else:
                    zout.writestr(info, zin.read(info.filename))
            for part, data in replace.items():  # the newly added font parts
                zout.writestr(part, data)
    return True


# Elements that follow embeddedFontLst in CT_Presentation, in schema order.
_AFTER_EMBEDDED_FONTS = (
    "custShowLst",
    "photoAlbum",
    "custDataLst",
    "kinsoku",
    "defaultTextStyle",
    "modifyVerifier",
    "extLst",
)


def _add_embedded_fonts(presentation: str, new_fonts: dict[str, dict[str, str]]) -> str:
    entries = "".join(
        f'<p:embeddedFont><p:font typeface="{_xml_attr(family)}"/>'
        + "".join(
            f'<p:{style} r:id="{rid}"/>'
            for style, rid in sorted(styles.items(), key=lambda s: STYLES.index(s[0]))
        )
        + "</p:embeddedFont>"
        for family, styles in new_fonts.items()
    )
    if "<p:embeddedFontLst>" in presentation:
        return presentation.replace("</p:embeddedFontLst>", entries + "</p:embeddedFontLst>", 1)
    block = f"<p:embeddedFontLst>{entries}</p:embeddedFontLst>"
    for tag in _AFTER_EMBEDDED_FONTS:
        match = re.search(rf"<p:{tag}\b", presentation)
        if match:
            return presentation[: match.start()] + block + presentation[match.start() :]
    return presentation.replace("</p:presentation>", block + "</p:presentation>", 1)


def _xml_attr(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def font_file(family: str, style: str) -> Path | None:
    """A cached font file for the browser, if some template brought it."""
    if style not in STYLES or not _safe_family(family):
        return None
    path = CACHE_DIR / "families" / family / f"{style}.ttf"
    return path if path.is_file() else None


def font_css(families: list[str], url_for) -> str:
    """@font-face rules for every cached style of `families`; `url_for(family, style)` -> URL."""
    rules = []
    for family in families:
        for style in STYLES:
            if font_file(family, style) is None:
                continue
            rules.append(
                "@font-face{"
                f'font-family:"{family.replace(chr(34), "")}";'
                f"font-weight:{700 if 'bold' in style.lower() else 400};"
                f"font-style:{'italic' if 'italic' in style.lower() else 'normal'};"
                f'src:url("{url_for(family, style)}") format("truetype");'
                "font-display:swap}"
            )
    return "\n".join(rules)


# --- metrics ------------------------------------------------------------------

# Text the average character width is measured on: ordinary Russian and
# English prose, as generated slides read. design_system.textfit's
# REFERENCE_CHAR_WIDTH_EM is Arial measured on this same sample.
WIDTH_SAMPLE = (
    "Рост выручки составил 24% за второй квартал, клиенты довольны сервисом. "
    "Revenue grew 24% in the second quarter and customers love the service."
)
# Advance assumed for characters a font lacks (the renderer falls back to a
# system font for them — Cyrillic in a Latin-only display face, typically).
_FALLBACK_EM = 0.55


def char_width_em(ttf: bytes) -> float:
    """Average advance of `ttf` over WIDTH_SAMPLE, in em."""
    font = TTFont(io.BytesIO(ttf), lazy=True)
    cmap = font.getBestCmap() or {}
    metrics = font["hmtx"]
    upm = font["head"].unitsPerEm
    total = 0.0
    for ch in WIDTH_SAMPLE:
        glyph = cmap.get(ord(ch))
        total += metrics[glyph][0] / upm if glyph else _FALLBACK_EM
    return round(total / len(WIDTH_SAMPLE), 3)


def annotate_char_widths(deck, pptx: Path) -> None:
    """Set `char_width_em` on every run of `deck` (parsed from `pptx`) whose font we have.

    Bold runs get the bold face's width when there is one. Runs in fonts we
    don't have (system fonts, unavailable families) stay None — consumers
    then assume a typical sans.
    """
    widths: dict[tuple[str, bool], float] = {}
    for family, styles in template_fonts(pptx).items():
        for style, ttf in styles.items():
            if style in ("regular", "bold"):
                widths[(family, style == "bold")] = char_width_em(ttf)
    if not widths:
        return
    for slide in deck.slides:
        for shape in slide.shapes:
            paragraphs = list(getattr(shape, "paragraphs", []))
            for row in getattr(shape, "rows", []) or []:
                for cell in row:
                    paragraphs += cell.paragraphs
            for paragraph in paragraphs:
                for run in paragraph.runs:
                    if run.font_name is None:
                        continue
                    bold = bool(run.bold)
                    width = widths.get((run.font_name, bold)) or widths.get(
                        (run.font_name, not bold)
                    )
                    if width is not None:
                        run.char_width_em = width
