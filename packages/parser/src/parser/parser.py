"""PPTX -> IR parsing.

`parse()` walks every slide's shape tree with `python-pptx` and builds a
`Deck`. Nothing here assumes a particular template: shape kinds are dispatched
on `python-pptx`'s own `MSO_SHAPE_TYPE`, and anything not explicitly handled
falls through to `PassthroughShape` with its raw XML preserved.
"""

from __future__ import annotations

import base64
from pathlib import Path

from ir_schema import (
    AutoShape,
    Color,
    Deck,
    Paragraph,
    PassthroughShape,
    Picture,
    Slide,
    Table,
    TableCell,
    TextBoxShape,
    TextRun,
)
from lxml import etree
from pptx import Presentation
from pptx.dml.color import ColorFormat
from pptx.dml.fill import FillFormat
from pptx.enum.dml import MSO_FILL_TYPE
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.shapes.base import BaseShape
from pptx.text.text import Font, TextFrame

# MSO_THEME_COLOR member name -> the OOXML <a:schemeClr val="..."> slot it
# corresponds to. NOT_THEME_COLOR/MIXED are intentionally absent: callers
# treat an unmapped name as unresolvable, same as any other lookup miss.
_THEME_COLOR_SLOT = {
    "DARK_1": "dk1",
    "LIGHT_1": "lt1",
    "DARK_2": "dk2",
    "LIGHT_2": "lt2",
    "ACCENT_1": "accent1",
    "ACCENT_2": "accent2",
    "ACCENT_3": "accent3",
    "ACCENT_4": "accent4",
    "ACCENT_5": "accent5",
    "ACCENT_6": "accent6",
    "HYPERLINK": "hlink",
    "FOLLOWED_HYPERLINK": "folHlink",
    "BACKGROUND_1": "bg1",
    "BACKGROUND_2": "bg2",
    "TEXT_1": "tx1",
    "TEXT_2": "tx2",
}

# The 12 slots a <a:clrScheme> defines directly.
_RAW_THEME_SLOTS = [
    "dk1", "lt1", "dk2", "lt2",
    "accent1", "accent2", "accent3", "accent4", "accent5", "accent6",
    "hlink", "folHlink",
]
# The 4 semantic slots a slide master's <p:clrMap> indirects to one of the
# raw slots above (accent1-6/hlink/folHlink always map to themselves).
_SEMANTIC_THEME_SLOTS = ["bg1", "tx1", "bg2", "tx2"]

_A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_P_NS = "{http://schemas.openxmlformats.org/presentationml/2006/main}"


def parse(path: Path) -> Deck:
    presentation = Presentation(str(path))
    theme_colors = _resolve_deck_theme_colors(presentation)
    slides = [
        _parse_slide(index, slide) for index, slide in enumerate(presentation.slides)
    ]
    return Deck(
        slide_width=presentation.slide_width,
        slide_height=presentation.slide_height,
        source_path=str(path),
        slides=slides,
        theme_colors=theme_colors,
    )


def _parse_slide(index: int, slide) -> Slide:
    # Templates carry stray trailing spaces in layout names ("Мокап телефона ");
    # the model drops them, so exact-match role lookups would otherwise fail.
    layout_name = slide.slide_layout.name.strip()
    shapes = [
        _parse_shape(shape, z_order)
        for z_order, shape in enumerate(slide.shapes)
    ]
    return Slide(
        index=index,
        layout_name=layout_name,
        shapes=shapes,
        background=_resolve_slide_background(slide),
    )


def _resolve_deck_theme_colors(presentation) -> dict[str, str]:
    """Resolve every theme color slot to a hex string for this deck.

    A deck can have multiple slide masters with genuinely different themes
    (observed in real templates, e.g. vk-education.pptx and vktech.pptx both
    have 2 masters with distinct theme parts). `Deck.theme_colors` is a
    single flat dict shared by the whole deck, so full per-master accuracy
    is out of scope here (per ticket instructions) -- we resolve against the
    *first* slide master's theme. This is exactly correct for every
    single-master template (the common case, including
    evals/templates/portrait-regiona.pptx, the template motivating this
    ticket) and a documented approximation for multi-master decks: a slide
    belonging to a later master may have `Color.theme_color` slots that
    resolve to the wrong hex via this dict. Making that fully correct would
    need a per-slide or per-master color mapping, which is a bigger change
    than this ticket calls for.
    """
    if not presentation.slide_masters:
        return {}
    master = presentation.slide_masters[0]

    theme_part = master.part.part_related_by(RT.THEME)
    theme_xml = etree.fromstring(theme_part.blob)
    clr_scheme = theme_xml.find(f".//{_A_NS}clrScheme")
    if clr_scheme is None:
        return {}

    raw: dict[str, str] = {}
    for slot in _RAW_THEME_SLOTS:
        slot_el = clr_scheme.find(f"{_A_NS}{slot}")
        if slot_el is None:
            continue
        hex_value = _extract_theme_color_hex(slot_el)
        if hex_value is not None:
            raw[slot] = hex_value

    resolved = dict(raw)
    clr_map = master.element.find(f".//{_P_NS}clrMap")
    if clr_map is not None:
        for semantic_slot in _SEMANTIC_THEME_SLOTS:
            target_slot = clr_map.get(semantic_slot)
            if target_slot and target_slot in raw:
                resolved[semantic_slot] = raw[target_slot]

    return resolved


def _extract_theme_color_hex(slot_element) -> str | None:
    srgb = slot_element.find(f"{_A_NS}srgbClr")
    if srgb is not None:
        val = srgb.get("val")
        if val:
            return val.upper()
    sys_color = slot_element.find(f"{_A_NS}sysClr")
    if sys_color is not None:
        last_color = sys_color.get("lastClr")
        if last_color:
            return last_color.upper()
    return None


def _resolve_slide_background(slide) -> Color | None:
    for source in (slide, slide.slide_layout, slide.slide_layout.slide_master):
        color = _resolve_fill_color(source.background.fill)
        if color is not None:
            return color
    return None


def _resolve_fill_color(fill: FillFormat) -> Color | None:
    try:
        fill_type = fill.type
    except (ValueError, AttributeError, TypeError):
        return None
    if fill_type != MSO_FILL_TYPE.SOLID:
        return None
    try:
        fore_color = fill.fore_color
    except (ValueError, AttributeError, TypeError):
        return None
    return _parse_color(fore_color)


def _placeholder_fields(shape: BaseShape) -> dict:
    if not shape.is_placeholder:
        return {"is_placeholder": False}
    ph_format = shape.placeholder_format
    return {
        "is_placeholder": True,
        "placeholder_type": str(ph_format.type) if ph_format.type is not None else None,
        "placeholder_idx": ph_format.idx,
    }


def _shape_base_fields(shape: BaseShape, z_order: int) -> dict:
    return {
        "shape_id": shape.shape_id,
        "name": shape.name,
        "z_order": z_order,
        "left": shape.left if shape.left is not None else 0,
        "top": shape.top if shape.top is not None else 0,
        "width": shape.width if shape.width is not None else 0,
        "height": shape.height if shape.height is not None else 0,
        "rotation": shape.rotation or 0.0,
        **_placeholder_fields(shape),
    }


def _parse_shape(shape: BaseShape, z_order: int) -> object:
    shape_type = shape.shape_type

    if shape.has_table:
        return _parse_table(shape, z_order)
    if shape_type == MSO_SHAPE_TYPE.PICTURE:
        return _parse_picture(shape, z_order)
    if shape_type in (MSO_SHAPE_TYPE.TEXT_BOX, MSO_SHAPE_TYPE.PLACEHOLDER):
        return _parse_text_box(shape, z_order)
    if shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE:
        return _parse_autoshape(shape, z_order)

    return _parse_passthrough(shape, z_order)


def _parse_text_box(shape: BaseShape, z_order: int) -> TextBoxShape:
    return TextBoxShape(
        **_shape_base_fields(shape, z_order),
        paragraphs=_parse_text_frame(shape.text_frame) if shape.has_text_frame else [],
    )


def _parse_autoshape(shape: BaseShape, z_order: int) -> AutoShape:
    autoshape_type = None
    try:
        if shape.auto_shape_type is not None:
            autoshape_type = str(shape.auto_shape_type)
    except (ValueError, AttributeError):
        pass

    fill_color = None
    try:
        if shape.fill.type is not None:
            fill_color = _parse_color(shape.fill.fore_color)
    except (ValueError, AttributeError, TypeError):
        pass

    return AutoShape(
        **_shape_base_fields(shape, z_order),
        autoshape_type=autoshape_type,
        fill_color=fill_color,
        paragraphs=_parse_text_frame(shape.text_frame) if shape.has_text_frame else [],
    )


def _parse_picture(shape: BaseShape, z_order: int) -> Picture:
    image = shape.image
    crop_left = shape.crop_left or 0.0
    crop_top = shape.crop_top or 0.0
    crop_right = shape.crop_right or 0.0
    crop_bottom = shape.crop_bottom or 0.0
    return Picture(
        **_shape_base_fields(shape, z_order),
        image_bytes_b64=_b64encode(image.blob),
        content_type=image.content_type,
        filename=image.filename,
        crop_left=crop_left,
        crop_top=crop_top,
        crop_right=crop_right,
        crop_bottom=crop_bottom,
    )


def _parse_table(shape: BaseShape, z_order: int) -> Table:
    table = shape.table
    rows = [
        [TableCell(paragraphs=_parse_text_frame(cell.text_frame)) for cell in row.cells]
        for row in table.rows
    ]
    return Table(
        **_shape_base_fields(shape, z_order),
        rows=rows,
        column_widths=[col.width for col in table.columns],
        row_heights=[row.height for row in table.rows],
    )


def _parse_passthrough(shape: BaseShape, z_order: int) -> PassthroughShape:
    return PassthroughShape(
        **_shape_base_fields(shape, z_order),
        original_shape_type=str(shape.shape_type) if shape.shape_type is not None else None,
        raw_xml=etree.tostring(shape._element, encoding="unicode"),
    )


def _parse_text_frame(text_frame: TextFrame) -> list[Paragraph]:
    return [_parse_paragraph(paragraph) for paragraph in text_frame.paragraphs]


def _parse_paragraph(paragraph) -> Paragraph:
    runs = [_parse_run(run) for run in paragraph.runs]
    if not runs:
        # An empty slot (typically a placeholder awaiting text) has no runs,
        # but its end-of-paragraph properties say how typed text will look —
        # often 40pt+ on a title slide. Without them every capacity and
        # shrink-to-fit estimate falls back to a generic 18pt and badly
        # overestimates how much text fits. Kept as one empty-text run so
        # "has text" checks are unaffected.
        end = paragraph._p.find(qn("a:endParaRPr"))
        if end is not None and end.get("sz"):
            runs = [_style_run("", Font(end))]
    return Paragraph(
        runs=runs,
        alignment=str(paragraph.alignment) if paragraph.alignment is not None else None,
        level=paragraph.level or 0,
    )


def _parse_run(run) -> TextRun:
    return _style_run(run.text, run.font)


def _style_run(text: str, font: Font) -> TextRun:
    return TextRun(
        text=text,
        font_name=font.name,
        font_size_pt=font.size.pt if font.size is not None else None,
        bold=font.bold,
        italic=font.italic,
        underline=font.underline if isinstance(font.underline, bool) else None,
        color=_parse_color(font.color),
    )


def _parse_color(color_format: ColorFormat) -> Color | None:
    try:
        color_type = color_format.type
    except AttributeError:
        return None
    if color_type is None:
        return None

    if color_type.name == "RGB":
        return Color(kind="rgb", rgb=str(color_format.rgb))
    if color_type.name == "SCHEME":
        slot = _THEME_COLOR_SLOT.get(color_format.theme_color.name)
        if slot is None:
            return None
        return Color(kind="theme", theme_color=slot)
    return None


def _b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")
