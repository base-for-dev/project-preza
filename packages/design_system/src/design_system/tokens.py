"""IR -> design tokens: color palette and typography.

Extraction is purely statistical over whatever the IR already carries (`Color`,
`TextRun.font_name`, `TextRun.font_size_pt`, `AutoShape.fill_color`) — no
template-specific field names or values are assumed. See ARCHITECTURE.md and
this package's module docstring in `__init__.py` for how this fits the
pipeline.
"""

from __future__ import annotations

from collections import Counter

from ir_schema import AutoShape, Color, Deck, Table, TextBoxShape
from pydantic import BaseModel

# A color/font/size that appears only once in a deck is more likely a typo,
# a one-off accent, or OCR/import noise than an actual palette member — a
# "palette" implies repeated, intentional use. Two occurrences is the lowest
# bar that distinguishes "used" from "used exactly once by accident". Decks
# too small to have any token repeat twice fall back to the full frequency
# list instead of returning nothing (see `_ranked` below).
MIN_OCCURRENCES = 2


class ColorToken(BaseModel):
    """A distinct color, keyed by how the IR represents it.

    `kind="rgb"` colors carry a literal hex value and are directly comparable
    across shapes (that's what `AUDIT.md`'s "color not in the template's
    palette" check needs). `kind="theme"` colors only carry a theme slot name
    (e.g. `ACCENT_1`) — the IR doesn't resolve theme colors to RGB, so these
    are kept distinct rather than guessed at.
    """

    kind: str
    value: str
    count: int


class FontToken(BaseModel):
    name: str
    count: int


class SizeToken(BaseModel):
    size_pt: float
    count: int


class Typography(BaseModel):
    fonts: list[FontToken]
    type_scale: list[SizeToken]


def _ranked(counter: Counter, min_occurrences: int = MIN_OCCURRENCES) -> list[tuple]:
    """Frequency-rank counter items, most-used first; ties broken by key for determinism.

    Filters to items seen at least `min_occurrences` times, since that's what
    distinguishes a "palette" from incidental one-off usage. If filtering
    would remove everything (e.g. a tiny deck where nothing repeats), falls
    back to the unfiltered ranked list — an empty palette is a worse answer
    than a low-confidence one, and callers can still see `count` per entry to
    apply their own cutoff.
    """
    if not counter:
        return []
    filtered = {k: v for k, v in counter.items() if v >= min_occurrences}
    items = filtered if filtered else dict(counter)
    return sorted(items.items(), key=lambda kv: (-kv[1], str(kv[0])))


def _color_key(color: Color) -> tuple[str, str] | None:
    if color.kind == "rgb" and color.rgb:
        return ("rgb", color.rgb)
    if color.kind == "theme" and color.theme_color:
        return ("theme", color.theme_color)
    return None


def extract_colors(deck: Deck) -> list[ColorToken]:
    """Rank the deck's distinct colors by frequency of use.

    Sources: text run colors (any shape with paragraphs) and autoshape fills.
    Table cells are covered too since `TableCell.paragraphs` carries runs the
    same way a text box does; `Table` itself has no per-cell fill field in the
    IR today, so cell background color isn't extracted (nothing to read).
    """
    counter: Counter[tuple[str, str]] = Counter()

    for slide in deck.slides:
        for shape in slide.shapes:
            if isinstance(shape, (TextBoxShape, AutoShape)):
                for paragraph in shape.paragraphs:
                    for run in paragraph.runs:
                        if run.color:
                            key = _color_key(run.color)
                            if key:
                                counter[key] += 1
            if isinstance(shape, AutoShape) and shape.fill_color:
                key = _color_key(shape.fill_color)
                if key:
                    counter[key] += 1
            if isinstance(shape, Table):
                for row in shape.rows:
                    for cell in row:
                        for paragraph in cell.paragraphs:
                            for run in paragraph.runs:
                                if run.color:
                                    key = _color_key(run.color)
                                    if key:
                                        counter[key] += 1

    return [
        ColorToken(kind=kind, value=value, count=count) for (kind, value), count in _ranked(counter)
    ]


def extract_typography(deck: Deck) -> Typography:
    """Rank the deck's distinct font families and font sizes by frequency of use."""
    font_counter: Counter[str] = Counter()
    size_counter: Counter[float] = Counter()

    for slide in deck.slides:
        for shape in slide.shapes:
            paragraph_lists = []
            if isinstance(shape, (TextBoxShape, AutoShape)):
                paragraph_lists.append(shape.paragraphs)
            if isinstance(shape, Table):
                for row in shape.rows:
                    for cell in row:
                        paragraph_lists.append(cell.paragraphs)

            for paragraphs in paragraph_lists:
                for paragraph in paragraphs:
                    for run in paragraph.runs:
                        if run.font_name:
                            font_counter[run.font_name] += 1
                        if run.font_size_pt is not None:
                            size_counter[run.font_size_pt] += 1

    fonts = [FontToken(name=name, count=count) for name, count in _ranked(font_counter)]
    sizes = [SizeToken(size_pt=size, count=count) for size, count in _ranked(size_counter)]
    sizes.sort(key=lambda t: t.size_pt)
    return Typography(fonts=fonts, type_scale=sizes)
