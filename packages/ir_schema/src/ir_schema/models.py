"""Pydantic models for the pipeline's intermediate representation (IR).

Scope is deliberately narrow: every field here must be populated from real
`python-pptx` data by `packages/parser`. Anything the parser can't safely
interpret (charts, SmartArt, groups, OLE objects, ...) becomes a
`PassthroughShape` carrying the shape's raw XML instead of a best-guess model.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

Emu = int


class Color(BaseModel):
    """A resolved or theme-relative color, as `python-pptx` exposes it.

    `kind="rgb"` carries a literal hex color. `kind="theme"` carries the name
    of a theme color slot (e.g. `ACCENT_1`) instead of a hex value, since the
    actual RGB depends on the theme and isn't fixed at the run level.
    """

    kind: Literal["rgb", "theme"]
    rgb: str | None = None
    theme_color: str | None = None


class TextRun(BaseModel):
    text: str
    font_name: str | None = None
    font_size_pt: float | None = None
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    color: Color | None = None


class Paragraph(BaseModel):
    runs: list[TextRun] = Field(default_factory=list)
    alignment: str | None = None
    level: int = 0


class ShapeBase(BaseModel):
    shape_id: int
    name: str
    z_order: int
    left: Emu
    top: Emu
    width: Emu
    height: Emu
    rotation: float = 0.0
    is_placeholder: bool = False
    placeholder_type: str | None = None
    placeholder_idx: int | None = None


class TextBoxShape(ShapeBase):
    kind: Literal["text_box"] = "text_box"
    paragraphs: list[Paragraph] = Field(default_factory=list)


class AutoShape(ShapeBase):
    kind: Literal["autoshape"] = "autoshape"
    autoshape_type: str | None = None
    fill_color: Color | None = None
    paragraphs: list[Paragraph] = Field(default_factory=list)


class Picture(ShapeBase):
    kind: Literal["picture"] = "picture"
    image_bytes_b64: str | None = None
    content_type: str | None = None
    filename: str | None = None
    crop_left: float = 0.0
    crop_top: float = 0.0
    crop_right: float = 0.0
    crop_bottom: float = 0.0
    # Set only when this image was swapped in by internet photo search (see
    # packages/images) — Unsplash's API terms require visible attribution
    # ("Photo by {name} on Unsplash", linked) wherever the photo is shown.
    # None for the template's own original image — nothing to attribute.
    attribution_text: str | None = None
    attribution_url: str | None = None


class TableCell(BaseModel):
    paragraphs: list[Paragraph] = Field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(
            "".join(run.text for run in paragraph.runs) for paragraph in self.paragraphs
        )


class Table(ShapeBase):
    kind: Literal["table"] = "table"
    rows: list[list[TableCell]] = Field(default_factory=list)
    column_widths: list[Emu] = Field(default_factory=list)
    row_heights: list[Emu] = Field(default_factory=list)


class PassthroughShape(ShapeBase):
    """Fallback for shape kinds the pipeline doesn't model yet.

    Covers charts, SmartArt, groups, OLE/media objects, and connectors.
    `raw_xml` preserves the shape's `<p:sp>`/`<p:graphicFrame>`/... element
    verbatim so nothing is lost, even though `export` currently skips it.
    """

    kind: Literal["passthrough"] = "passthrough"
    original_shape_type: str | None = None
    raw_xml: str


Shape = Annotated[
    TextBoxShape | AutoShape | Picture | Table | PassthroughShape,
    Field(discriminator="kind"),
]


class Slide(BaseModel):
    index: int
    layout_name: str
    shapes: list[Shape] = Field(default_factory=list)
    background: Color | None = None
    """The slide's effectively resolved background fill (solid color only).

    Resolved by walking slide -> slide layout -> slide master until a solid
    fill is found. `None` means nothing resolved (gradient/picture/pattern
    fill, or genuinely nothing set) -- a legitimate "renderer should default
    to white" signal, not a bug.
    """
    notes: str | None = None
    """Speaker notes: what the presenter says over this slide.

    Filled by `layout.compose_deck` from generated content; written to the
    slide's notes page on `.pptx` export. `None` for template slides.
    """


class Deck(BaseModel):
    slide_width: Emu
    slide_height: Emu
    source_path: str | None = None
    slides: list[Slide] = Field(default_factory=list)
    theme_colors: dict[str, str] = Field(default_factory=dict)
    """Every theme color slot (`dk1`, `lt1`, `dk2`, `lt2`, `accent1`..`accent6`,
    `hlink`, `folHlink`, `bg1`, `tx1`, `bg2`, `tx2`) resolved to a 6-hex-digit
    RGB string (no `#`), keyed by the exact slot name found in
    `Color.theme_color` elsewhere in the IR. A consumer never needs to
    understand OOXML's `clrMap` indirection: `deck.theme_colors[color.theme_color]`
    is always a hex string when the slot was resolvable.
    """
