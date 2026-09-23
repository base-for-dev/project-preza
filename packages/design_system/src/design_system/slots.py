"""Template slide structure: what content slots does a slide actually offer?

A layout name ("MAIN_POINT", "15_Титульный слайд") says nothing on its own
about how a slide is built — one text block? three cards? a table? Both the
LLM stages (`generator`: which layout to pick, how much to write) and the
composer (`layout`: where to put it) need the same answer, so the analysis
lives here, below both, and is purely structural over the IR — no names,
positions-as-labels, or locale assumptions (ARCHITECTURE.md's generalization
requirement).

The key signal for "parallel content slots" (a card grid, a column row) is
several text shapes of *exactly* the same kind and size that already carry
text: a designer draws one card and duplicates it, so identical geometry means
"one item each", not "one shape".
"""

from __future__ import annotations

import re
from collections import Counter

from ir_schema import AutoShape, Deck, Picture, Shape, Slide, Table, TextBoxShape
from pydantic import BaseModel

_TITLE_KINDS = {"TITLE", "CENTER_TITLE"}
_BODY_KINDS = {"BODY", "SUBTITLE", "OBJECT"}

TextShape = TextBoxShape | AutoShape

# Fixed UI chrome a template author leaves as a short label on a shape that
# isn't a content slot at all — a QR-code box, a "visit our site" link badge,
# a logo mark. Confirmed live: a shape template-labeled exactly "QR-code" was
# picked as "the one body shape" (it's the single largest fallback candidate
# by area, being a big decorative square) and got 4 full sentences crammed
# into it — a slide meant for a call-to-action + QR code, not a bullet list.
# Matched against the shape's ORIGINAL template text (before any generated
# content overwrites it), case-insensitively, as a short exact-ish label —
# `re.fullmatch` on the stripped text, so a real sentence that happens to
# contain "link" isn't caught, only a shape whose *entire* original content
# is one of these bare tokens.
_CHROME_LABELS = re.compile(
    r"(qr[\s\-]?код|qr[\s\-]?code|ссылка(\s+на\s+сайт)?|link|url|"
    r"лого(тип)?|logo|сайт|веб-?сайт|website)",
    re.IGNORECASE,
)


def is_functional_chrome(shape: TextShape) -> bool:
    """True if the shape's own template text is a bare UI-chrome label.

    Only fires on short original text (<=20 chars, no more than a couple of
    words) so a real bullet that happens to use one of these words in a full
    sentence is never mistaken for chrome — this targets the specific case
    of a shape whose *entire* content is a placeholder word.
    """
    text = " ".join(run.text for p in shape.paragraphs for run in p.runs).strip()
    if not text or len(text) > 20:
        return False
    return bool(_CHROME_LABELS.fullmatch(text))


# "ХХ" / "XX" / "ХХ%" (Cyrillic or Latin X, 2+ repeated, optional percent/
# decimal) is a template author's own placeholder for "a number goes here" —
# the same convention as "lorem ipsum" for prose, used specifically on chart/
# data-annotation slides (confirmed live: a "Графики" layout with a background
# chart picture and several "ХХ"/"ХХ%" callout labels meant to annotate
# specific points on that chart). There is no way for content generation to
# know what number belongs at a specific point on an arbitrary background
# chart image, so these must never be filled — the alternative (observed
# live) is content written for a *different* slot landing in one "ХХ" shape
# while its siblings are left as literal "XX", a garbled mix of real and
# placeholder text on the same slide.
_DATA_PLACEHOLDER = re.compile(r"[xXхХ]{2,}\s*%?|[xXхХ]{1,2}[.,][xXхХ]", re.IGNORECASE)


def is_data_placeholder(shape: TextShape) -> bool:
    """True if the shape's own template text is a bare "insert a number" token."""
    text = " ".join(run.text for p in shape.paragraphs for run in p.runs).strip()
    if not text or len(text) > 10:
        return False
    return bool(_DATA_PLACEHOLDER.fullmatch(text))


# A shape styled at display/hero size (a big stat number, a giant "Q&A" or
# section-break word) with short original text is a design accent, not a
# paragraph container — confirmed live twice: a shape template-labeled
# "ХХХ%данные показателя" at 80pt, and one labeled "Q&A" at 144pt, both got
# picked as "the fallback body shape" (largest textful candidate by area)
# and inherited real multi-sentence content at their sampled huge font size,
# overflowing badly. Normal body/bullet text in these templates tops out
# around 24pt (see AUDIT.md's density checks) — 40pt+ on a short label is a
# reliable non-keyword signal, unlike `is_functional_chrome`'s wordlist.
_DISPLAY_ACCENT_MAX_CHARS = 30
_DISPLAY_ACCENT_MIN_FONT_PT = 40.0


def is_display_accent(shape: TextShape) -> bool:
    """True if the shape's own template text+style reads as a display accent."""
    text = " ".join(run.text for p in shape.paragraphs for run in p.runs).strip()
    if not text or len(text) > _DISPLAY_ACCENT_MAX_CHARS:
        return False
    sizes = [
        run.font_size_pt for p in shape.paragraphs for run in p.runs if run.font_size_pt is not None
    ]
    return bool(sizes) and max(sizes) >= _DISPLAY_ACCENT_MIN_FONT_PT


def is_non_content_shape(shape: TextShape) -> bool:
    """Combined "never a fill target" signal: chrome, an accent, or a data placeholder."""
    return is_functional_chrome(shape) or is_display_accent(shape) or is_data_placeholder(shape)


def placeholder_kind(shape: Shape) -> str | None:
    """Bare placeholder-type name, e.g. "TITLE" from python-pptx's "TITLE (1)"."""
    if shape.placeholder_type is None:
        return None
    return shape.placeholder_type.split(" (", 1)[0]


def is_title(shape: Shape) -> bool:
    return placeholder_kind(shape) in _TITLE_KINDS


def is_body_placeholder(shape: Shape) -> bool:
    return placeholder_kind(shape) in _BODY_KINDS


def shape_has_text(shape: TextShape) -> bool:
    return any(run.text.strip() for p in shape.paragraphs for run in p.runs)


def repeated_slot_groups(candidates: list[TextShape]) -> list[list[TextShape]]:
    """Groups of >=2 identically-sized, same-kind text shapes, biggest group first.

    Only shapes that already carry text qualify, so decorative same-size
    rectangles (no text) aren't mistaken for content slots. Each group is
    ordered the way a reader scans it: top-to-bottom, then left-to-right.
    """
    by_size: dict[tuple[str, int, int], list[TextShape]] = {}
    for shape in candidates:
        if not shape_has_text(shape):
            continue
        by_size.setdefault((shape.kind, shape.width, shape.height), []).append(shape)
    groups = [g for g in by_size.values() if len(g) >= 2]
    groups.sort(key=lambda g: g[0].width * g[0].height, reverse=True)
    return [sorted(g, key=lambda s: (s.top, s.left)) for g in groups]


class SlotSummary(BaseModel):
    """What one template slide offers to fill, in content terms."""

    has_title: bool = False
    # BODY/SUBTITLE/OBJECT placeholders (free-text areas).
    body_slots: int = 0
    # Size of the largest group of identical text shapes (cards/columns); 0 if none.
    card_slots: int = 0
    has_table: bool = False
    has_picture: bool = False
    # The title placeholder's own sampled font size, when large — a title
    # slot styled at display size (confirmed live: 144pt on a "Q&A"-style
    # section-break slide) expects a punchy word/short phrase, not a full
    # sentence; writing a normal-length title there looks fine once the
    # renderer auto-shrinks it to fit, but defeats the layout's whole
    # purpose (a big, deliberately terse splash of text). None when the
    # title's font is normal body/heading size — no special instruction
    # needed. Threshold matches `is_display_accent`'s (40pt+).
    title_font_size_pt: float | None = None
    # Rough capacity of the roomiest free-text slot: how many lines fit its
    # height and how many characters fit one line at its font size. Lets the
    # writer size text to the box instead of stuffing three bullets into a
    # one-line strip (confirmed live: 3 bullets into a 0.3in-tall shape).
    # None when the slide has no free-text body slot.
    body_lines: int | None = None
    body_chars_per_line: int | None = None

    @property
    def kind(self) -> str:
        """Coarse structural class, used to group slides and to describe them."""
        if self.card_slots >= 2:
            return "cards"
        if self.has_table:
            return "table"
        if self.body_slots >= 1:
            return "body"
        return "title_only"


def describe_slots(slide: Slide) -> SlotSummary:
    """Structural summary of one template slide."""
    title = False
    title_font_size: float | None = None
    body = 0
    body_shapes: list[TextShape] = []
    fallback: list[TextShape] = []
    table = False
    picture = False

    for shape in slide.shapes:
        if isinstance(shape, Picture):
            picture = True
        elif isinstance(shape, Table):
            table = True
        elif isinstance(shape, (TextBoxShape, AutoShape)):
            if is_title(shape):
                title = True
                sizes = [
                    run.font_size_pt
                    for p in shape.paragraphs
                    for run in p.runs
                    if run.font_size_pt is not None
                ]
                if sizes and max(sizes) >= _DISPLAY_ACCENT_MIN_FONT_PT:
                    title_font_size = max(sizes)
            elif is_body_placeholder(shape):
                body += 1
                body_shapes.append(shape)
            elif not is_non_content_shape(shape):
                fallback.append(shape)

    cards = 0
    # Cards only apply when there is no real body placeholder (same precedence
    # the composer uses: body placeholders win, then repeated groups).
    if body == 0:
        groups = repeated_slot_groups(fallback)
        if groups:
            cards = len(groups[0])
        elif any(shape_has_text(s) for s in fallback):
            # A lone free text shape acts as the body (composer's last resort).
            body = 1
            body_shapes = [s for s in fallback if shape_has_text(s)][:1]

    body_lines, body_chars = _text_capacity(body_shapes)

    return SlotSummary(
        has_title=title,
        body_slots=body,
        card_slots=cards,
        has_table=table,
        has_picture=picture,
        title_font_size_pt=title_font_size,
        body_lines=body_lines,
        body_chars_per_line=body_chars,
    )


_EMU_PER_PT = 12700
_DEFAULT_BODY_PT = 18.0
_LINE_HEIGHT = 1.2
_AVG_CHAR_WIDTH_EM = 0.5


def _text_capacity(shapes: list[TextShape]) -> tuple[int | None, int | None]:
    """(lines, chars per line) of the roomiest of `shapes`, or (None, None)."""
    best: tuple[int, int] | None = None
    for shape in shapes:
        sizes = [
            run.font_size_pt
            for p in shape.paragraphs
            for run in p.runs
            if run.font_size_pt is not None
        ]
        pt = max(sizes) if sizes else _DEFAULT_BODY_PT
        lines = max(1, int(shape.height / (pt * _LINE_HEIGHT * _EMU_PER_PT)))
        chars = max(8, int(shape.width / (pt * _AVG_CHAR_WIDTH_EM * _EMU_PER_PT)))
        if best is None or lines * chars > best[0] * best[1]:
            best = (lines, chars)
    return best if best else (None, None)


def representative_slots(slides: list[Slide]) -> SlotSummary:
    """The most common structure among a layout's slides (ties -> first seen).

    Instances of one layout can differ (some with a table, some without);
    the majority structure is the honest answer to "what is this layout?".
    """
    summaries = [describe_slots(s) for s in slides]
    counts = Counter(s.model_dump_json() for s in summaries)
    best = counts.most_common(1)[0][0]
    return next(s for s in summaries if s.model_dump_json() == best)


def pick_template_slides(roles: list[str], deck: Deck) -> list[Slide]:
    """The concrete template slide each generated slide will be built on.

    Several template slides can share one layout; repeated roles round-robin
    through them so consecutive same-layout slides don't all look identical.
    Content generation and composition MUST agree on this assignment — the
    text is written for one specific slide's slots — so both call this one
    function. Raises `ValueError` naming any role with no template slide.
    """
    by_role: dict[str, list[Slide]] = {}
    for slide in deck.slides:
        by_role.setdefault(slide.layout_name, []).append(slide)

    cursor: dict[str, int] = {}
    picked: list[Slide] = []
    for role in roles:
        candidates = by_role.get(role)
        if not candidates:
            raise ValueError(
                f"no template slide found for role {role!r} — available roles: {sorted(by_role)}"
            )
        i = cursor.get(role, 0)
        picked.append(candidates[i % len(candidates)])
        cursor[role] = i + 1
    return picked
