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

from ir_schema import AutoShape, Deck, PassthroughShape, Picture, Shape, Slide, Table, TextBoxShape
from pydantic import BaseModel

from design_system.textfit import width_scale

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
    return placeholder_kind(shape) in _TITLE_KINDS or shape.visual_title


# Visual title detection (see `mark_visual_titles`).
_VISUAL_TITLE_MIN_PT = 20.0
_VISUAL_TITLE_MAX_CHARS = 90
# How much bigger than every other text on the slide a heading must be set.
_VISUAL_TITLE_MARGIN = 1.15
_LETTERS = re.compile(r"[^\W\d_]", re.UNICODE)


def _max_size(shape: TextShape) -> float | None:
    sizes = [r.font_size_pt for p in shape.paragraphs for r in p.runs if r.font_size_pt]
    return max(sizes) if sizes else None


def visual_title(slide: Slide) -> TextShape | None:
    """The text box that reads as `slide`'s heading, when no placeholder is one.

    Most Google Slides / Canva templates have no title placeholders at all
    (84% of the sample library's slides) — the heading is just the biggest
    text. Without this, generation had nowhere to put a slide's title: the
    template's own heading ("Goal Roadmap", "Add a Roadmap Page") stayed on
    the slide, and a long heading that didn't read as a display accent became
    "the largest text box" and received the whole body at 100pt.

    The heading is the text set clearly largest on the slide (by
    `_VISUAL_TITLE_MARGIN`), at a heading size, reading as words — not a
    number ("01", "85%"), a data token, chrome, or a long paragraph. Ties
    (a row of same-size cards) mean there is no single heading.
    """
    if any(is_title(s) for s in slide.shapes):
        return None
    candidates = []
    others: list[float] = []
    for shape in slide.shapes:
        if not isinstance(shape, (TextBoxShape, AutoShape)) or not shape_has_text(shape):
            continue
        size = _max_size(shape)
        if size is None:
            continue
        text = " ".join(r.text for p in shape.paragraphs for r in p.runs).strip()
        if len(_LETTERS.findall(text)) < 4:
            # A giant "02", "85%", "“" or SWOT letter is decoration: it
            # neither is the heading nor outranks one.
            continue
        eligible = (
            size >= _VISUAL_TITLE_MIN_PT
            and len(text) <= _VISUAL_TITLE_MAX_CHARS
            and not is_functional_chrome(shape)
            and not is_data_placeholder(shape)
        )
        if eligible:
            candidates.append((size, shape))
        else:
            others.append(size)
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0], reverse=True)
    size, best = candidates[0]
    rivals = [s for s, _ in candidates[1:]] + others
    if any(r * _VISUAL_TITLE_MARGIN > size for r in rivals):
        return None
    return best


def mark_visual_titles(deck: Deck) -> Deck:
    """Flag each slide's visual heading (see `visual_title`) in place; returns `deck`."""
    for slide in deck.slides:
        title = visual_title(slide)
        if title is not None:
            title.visual_title = True
    return deck


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
    # A data chart (bar/line/pie...) from the template. Its sample data is
    # never shown: composition fills it from the writer's numbers or removes it.
    has_chart: bool = False
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
    # Characters one card/column slot holds (lines x chars per line); None
    # when the slide has no card group.
    card_chars: int | None = None
    # Characters the title slot holds (a line more than fits its height, since
    # titles wrap generously); None when there is no title slot.
    title_chars: int | None = None
    # Characters the shape that receives `body` text holds — the second body
    # placeholder when the slide has two, else the (only) body shape.
    body_text_chars: int | None = None
    # Fields per card: 1 (just text) or 2 (a heading + its text, e.g. a
    # step's name over its description) — see `design_system.items`.
    card_fields: int = 1
    # Characters a card's heading holds (2-field cards only).
    card_heading_chars: int | None = None

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
    from design_system.items import find_items  # local: items builds on this module

    title = False
    title_font_size: float | None = None
    body = 0
    body_shapes: list[TextShape] = []
    title_shapes: list[TextShape] = []
    fallback: list[TextShape] = []
    table = False
    picture = False

    chart = any(isinstance(s, PassthroughShape) and s.is_chart for s in slide.shapes)
    for shape in slide.shapes:
        if (isinstance(shape, Picture) and not shape.is_background) or (
            isinstance(shape, TextBoxShape) and "PICTURE" in (shape.placeholder_type or "")
        ):
            picture = True
        elif isinstance(shape, Table):
            table = True
        elif isinstance(shape, (TextBoxShape, AutoShape)):
            if is_title(shape):
                title = True
                title_shapes.append(shape)
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
    card_chars: int | None = None
    # Cards only apply when there is no real body placeholder (same precedence
    # the composer uses: body placeholders win, then repeated groups).
    if body == 0:
        groups = repeated_slot_groups(fallback)
        if groups:
            cards = len(groups[0])
            card_lines, card_cpl = _text_capacity(groups[0][:1])
            if card_lines is not None and card_cpl is not None:
                card_chars = max(_MIN_CARD_CHARS, card_lines * card_cpl)
        elif any(shape_has_text(s) for s in fallback):
            # A lone free text shape acts as the body (composer's last resort).
            body = 1
            body_shapes = [max((s for s in fallback if shape_has_text(s)), key=_area)]

    # The composer puts bullets in the FIRST body shape and `body` in the
    # second, so capacity is that shape's — not the roomiest one's.
    body_lines, body_chars = _text_capacity(body_shapes[:1])
    body_text_chars = None
    if body_shapes:
        text_lines, text_cpl = _text_capacity(body_shapes[1:2] or body_shapes[:1])
        if text_lines is not None and text_cpl is not None:
            body_text_chars = text_lines * text_cpl
    plated = [title_on_plate(slide, t) for t in title_shapes[:1]]
    title_lines, title_cpl = _text_capacity(plated)
    # A free title may wrap one line past its box; a title on a plate may not
    # — the plate is exactly one pill tall.
    on_plate = bool(plated) and plated[0] is not title_shapes[0]
    extra_line = 0 if on_plate else 1
    title_chars = (title_lines + extra_line) * title_cpl if title_lines and title_cpl else None

    # A parallel item set (cards, steps, stats, team members — possibly built
    # from empty body placeholders and heading+text pairs) wins over the
    # plain body/card reading above; the composer applies the same rule.
    card_fields = 1
    card_heading_chars = None
    items = find_items(slide)
    if items:
        body, cards = 0, len(items)
        body_lines = body_chars = body_text_chars = None
        card_chars = _min_capacity([i.text for i in items])
        if card_chars is not None:
            card_chars = max(_MIN_CARD_CHARS, card_chars)
        if items[0].heading is not None:
            card_fields = 2
            card_heading_chars = _min_capacity([i.heading for i in items if i.heading])

    return SlotSummary(
        has_title=title,
        body_slots=body,
        card_slots=cards,
        has_table=table,
        has_picture=picture,
        has_chart=chart,
        title_font_size_pt=title_font_size,
        body_lines=body_lines,
        body_chars_per_line=body_chars,
        card_chars=card_chars,
        title_chars=title_chars,
        body_text_chars=body_text_chars,
        card_fields=card_fields,
        card_heading_chars=card_heading_chars,
    )


_MIN_CARD_CHARS = 12
_EMU_PER_PT = 12700
_DEFAULT_BODY_PT = 18.0
_LINE_HEIGHT = 1.2
_AVG_CHAR_WIDTH_EM = 0.5


def title_on_plate(slide: Slide, title: TextShape) -> TextShape:
    """The title sized to the coloured plate it sits on, or `title` itself.

    Templates often draw a short filled bar behind a much wider title box
    (seen live: a 3.4in pill behind a 10.8in title). Text past the bar's end
    runs off the plate onto the background, so the plate — not the box — is
    the real width a title has.
    """
    x = title.left + int(0.1 * 914_400)
    y = title.top + title.height // 2
    plates = [
        s
        for s in slide.shapes
        if isinstance(s, AutoShape)
        and not shape_has_text(s)
        and s.left <= x <= s.left + s.width
        and s.top <= y <= s.top + s.height
        and s.height < 3 * title.height + 914_400
        # A plate, not a full-width band or the slide's background panel.
        and s.width < 0.6 * max((o.left + o.width for o in slide.shapes), default=s.width)
    ]
    if not plates:
        return title
    plate = min(plates, key=lambda s: s.width * s.height)
    width = min(title.width, plate.left + plate.width - title.left)
    height = plate.top + plate.height - title.top
    return title.model_copy(
        update={
            "width": max(width, title.width // 4),
            "height": max(min(title.height, height), title.height // 2),
        }
    )


def _min_capacity(shapes: list[TextShape]) -> int | None:
    """Characters the smallest of `shapes` holds, or None if unmeasurable."""
    sizes = [
        lines * cpl
        for lines, cpl in (_text_capacity([s]) for s in shapes)
        if lines is not None and cpl is not None
    ]
    return min(sizes) if sizes else None


def _area(shape: TextShape) -> int:
    return max(shape.width, 0) * max(shape.height, 0)


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
        em = _AVG_CHAR_WIDTH_EM * width_scale([r for p in shape.paragraphs for r in p.runs])
        lines = max(1, int(shape.height / (pt * _LINE_HEIGHT * _EMU_PER_PT)))
        chars = max(8, int(shape.width / (pt * em * _EMU_PER_PT)))
        if best is None or lines * chars > best[0] * best[1]:
            best = (lines, chars)
    return best if best else (None, None)


def classify_shapes(slide: Slide) -> dict[int, str]:
    """shape_id -> the role the composer will treat that shape as.

    Roles: `title`, `body`, `card` (a repeated slot), `card_heading` (the
    heading field of a two-field card), `table`, `picture`,
    `chrome` (QR/logo/link label), `display_accent` (giant stat/splash text),
    `data_placeholder` ("ХХ%" chart callout), `text` (free text the composer
    only uses as a last resort) and `decor` (no text — background art).
    Mirrors `describe_slots` exactly so the template inspector shows what
    generation will really do, not a separate opinion.
    """
    from design_system.items import find_items  # local: items builds on this module

    roles: dict[int, str] = {}
    fallback: list[TextShape] = []
    has_body = False
    for shape in slide.shapes:
        if isinstance(shape, Picture):
            roles[shape.shape_id] = "decor" if shape.is_background else "picture"
        elif isinstance(shape, TextBoxShape) and "PICTURE" in (shape.placeholder_type or ""):
            roles[shape.shape_id] = "picture"
        elif isinstance(shape, Table):
            roles[shape.shape_id] = "table"
        elif isinstance(shape, (TextBoxShape, AutoShape)):
            if is_title(shape):
                roles[shape.shape_id] = "title"
            elif is_body_placeholder(shape):
                roles[shape.shape_id] = "body"
                has_body = True
            elif is_functional_chrome(shape):
                roles[shape.shape_id] = "chrome"
            elif is_data_placeholder(shape):
                roles[shape.shape_id] = "data_placeholder"
            elif is_display_accent(shape):
                roles[shape.shape_id] = "display_accent"
            elif not shape_has_text(shape):
                roles[shape.shape_id] = "decor"
            else:
                roles[shape.shape_id] = "text"
                fallback.append(shape)
        else:
            roles[shape.shape_id] = "decor"

    items = find_items(slide)
    if items:
        for item in items:
            roles[item.text.shape_id] = "card"
            if item.heading is not None:
                roles[item.heading.shape_id] = "card_heading"
        # Body placeholders outside the set can't exist (find_items rejects
        # that), but free text outside it is left alone as before.
        return roles
    if not has_body:
        groups = repeated_slot_groups(fallback)
        if groups:
            for member in groups[0]:
                roles[member.shape_id] = "card"
        elif fallback:
            roles[fallback[0].shape_id] = "body"
    return roles


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


_CATALOG_ROLE = re.compile(r"^([a-z]+)-\d{2}$")


def _family(layout_name: str) -> str:
    """A layout's family: the catalog purpose of a "team-09" role, else the layout name
    without a leading copy number."""
    m = _CATALOG_ROLE.match(layout_name)
    if m:
        return m.group(1)
    # "5_Контент", "7_Контент", "1_Контент" are numbered copies of one layout.
    return re.sub(r"^\d+_", "", layout_name)


def _signature(slide: Slide) -> tuple:
    s = describe_slots(slide)
    return (s.has_title, s.body_slots, s.card_slots, s.has_table, s.has_picture)


def _capacity(slide: Slide) -> tuple[int | None, int | None, int | None]:
    s = describe_slots(slide)
    body = s.body_lines * s.body_chars_per_line if s.body_lines and s.body_chars_per_line else None
    return (s.card_chars, body, s.title_chars)


# A substitute design must hold at least this share of the text the picked one
# was written for; smaller boxes would just overflow.
_MIN_CAPACITY_SHARE = 0.75


def _holds(candidate: Slide, baseline: Slide) -> bool:
    if candidate.index == baseline.index:
        return True
    return all(
        want is None or (have is not None and have >= _MIN_CAPACITY_SHARE * want)
        for want, have in zip(_capacity(baseline), _capacity(candidate), strict=True)
    )


def alternate_slides(picked: list[Slide], deck: Deck, shift: int) -> list[Slide]:
    """The same content on other designs of the same layout, `shift` steps along.

    For each slide in `picked`, the slides of `deck` from the same layout family
    with the same slots (title / text areas / cards / table / picture) and room
    for at least as much text are its equivalents — content written for one fits
    any of them. `shift` 0 keeps the baseline; 1, 2, ... move to the next
    equivalent, cyclically, so the three layout variants of one deck really are
    three different sets of the template's own designs rather than three copies
    of one. A slide with no equivalent stays as it is.
    """
    if shift == 0:
        return list(picked)
    same_shape: dict[tuple, list[Slide]] = {}
    out: list[Slide] = []
    for slide in picked:
        key = (_family(slide.layout_name), _signature(slide))
        if key not in same_shape:
            same_shape[key] = [
                s for s in deck.slides if (_family(s.layout_name), _signature(s)) == key
            ]
        pool = [s for s in same_shape[key] if _holds(s, slide)]
        at = next((i for i, s in enumerate(pool) if s.index == slide.index), 0)
        out.append(pool[(at + shift) % len(pool)])
    return out
