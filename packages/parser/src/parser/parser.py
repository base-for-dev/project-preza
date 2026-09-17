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
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.shapes.base import BaseShape
from pptx.text.text import TextFrame


def parse(path: Path) -> Deck:
    presentation = Presentation(str(path))
    slides = [
        _parse_slide(index, slide) for index, slide in enumerate(presentation.slides)
    ]
    return Deck(
        slide_width=presentation.slide_width,
        slide_height=presentation.slide_height,
        source_path=str(path),
        slides=slides,
    )


def _parse_slide(index: int, slide) -> Slide:
    layout_name = slide.slide_layout.name
    shapes = [
        _parse_shape(shape, z_order)
        for z_order, shape in enumerate(slide.shapes)
    ]
    return Slide(index=index, layout_name=layout_name, shapes=shapes)


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
    return Paragraph(
        runs=[_parse_run(run) for run in paragraph.runs],
        alignment=str(paragraph.alignment) if paragraph.alignment is not None else None,
        level=paragraph.level or 0,
    )


def _parse_run(run) -> TextRun:
    font = run.font
    return TextRun(
        text=run.text,
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
        return Color(kind="theme", theme_color=str(color_format.theme_color))
    return None


def _b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")
