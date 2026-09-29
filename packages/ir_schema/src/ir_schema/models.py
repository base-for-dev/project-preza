"""Pydantic models for the pipeline's intermediate representation (IR).

Scope is deliberately narrow: every field here must be populated from real
`python-pptx` data by `packages/parser`. Anything the parser can't safely
interpret (charts, SmartArt, groups, OLE objects, ...) becomes a
`PassthroughShape` carrying the shape's raw XML instead of a best-guess model.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

Emu = int

# `shape_id` of the Picture standing for a slide's own background image
# (`<p:bg>` filled with an image): not a shape in the file; listed so the
# slide's structure is complete, flagged `is_background` (never replaced).
BACKGROUND_SHAPE_ID = -1


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
    # Average character advance of this run's font, in em — measured from the
    # template's real font (export.fonts.annotate_char_widths); None when the
    # font file isn't available. Capacity and shrink-to-fit scale by it, so a
    # condensed font holds more text per line than a wide one.
    char_width_em: float | None = None


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
    # The slide's heading when it isn't a title placeholder — most Google
    # Slides / Canva templates set titles as plain text boxes. Set by
    # design_system.mark_visual_titles; treated exactly like a title placeholder.
    visual_title: bool = False
    # Set for a shape that lives inside a group: the id of the slide-level
    # group containing it. Its geometry is still slide-absolute (the group
    # transform applied); export finds it inside the group by `shape_id`.
    # Only text- or picture-bearing members are listed — the group itself
    # stays in the IR as a passthrough carrying the rest.
    group_id: int | None = None
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
    # True once the image has been swapped for something that isn't the
    # template's own picture (a search photo, the user's material, or a flat
    # stand-in colour) — export writes it into the file only then.
    image_replaced: bool = False
    # The image is the slide's backdrop — the slide's own background fill, or
    # a picture covering (nearly) the whole slide with content on top. It is
    # part of the design: never a photo slot, never replaced.
    is_background: bool = False


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
    chart_data: list[list[str]] | None = None
    """For a chart: new data composition put in (header row = category label
    then series names; each further row = category then values). Export
    writes it into the chart; `None` means the chart is exported as-is."""

    @property
    def is_chart(self) -> bool:
        return "CHART" in (self.original_shape_type or "") or "<c:chart " in self.raw_xml


ChartType = Literal["column", "bar", "line", "pie", "doughnut"]


class ChartSeries(BaseModel):
    name: str
    values: list[float]


class ChartShape(ShapeBase):
    """A chart the pipeline draws itself, exported as a native, editable chart.

    Unlike a `PassthroughShape` chart (the template's own, refilled with data),
    this exists only when the writer supplied numbers for a slide whose template
    slide has no chart to reuse. Colours and fonts come from the deck's theme.
    """

    kind: Literal["chart"] = "chart"
    chart_type: ChartType = "column"
    categories: list[str] = Field(default_factory=list)
    series: list[ChartSeries] = Field(default_factory=list)
    title: str = ""
    """A short caption above the chart ("Выручка, млн ₽"); empty for none."""
    unit: str = ""
    """What the values are measured in ("млн ₽", "%") — the value axis title."""
    category_label: str = ""
    """What the categories are ("Год", "Регион") — the category axis title."""
    font_size_pt: float | None = None
    font_name: str | None = None


# Pictograms the exporter can draw (see export.icons) — the writer picks from these.
ICON_NAMES = (
    "drop",
    "sun",
    "cloud",
    "leaf",
    "growth",
    "chart",
    "money",
    "users",
    "gear",
    "target",
    "idea",
    "check",
    "lock",
    "shield",
    "rocket",
    "time",
    "home",
    "globe",
    "heart",
    "star",
    "bolt",
    "phone",
    "mail",
    "database",
    "warning",
    "question",
)

DiagramType = Literal["process", "cycle", "hierarchy", "timeline", "icons"]


class DiagramItem(BaseModel):
    label: str
    detail: str = ""
    icon: str = ""
    """A pictogram name from `ICON_NAMES`; empty for none."""

    @field_validator("icon")
    @classmethod
    def _known_icon(cls, value: str) -> str:
        # A name the exporter cannot draw is dropped, never an error: the
        # diagram is still right without its picture.
        return value if value in ICON_NAMES else ""


class DiagramShape(ShapeBase):
    """A diagram or pictogram set, exported as a group of native shapes.

    The editable equivalent of SmartArt: every box, arrow and icon is a plain
    PowerPoint shape the user can recolour, move and retype.
    """

    kind: Literal["diagram"] = "diagram"
    diagram_type: DiagramType = "process"
    items: list[DiagramItem] = Field(default_factory=list)
    font_size_pt: float | None = None
    font_name: str | None = None


Shape = Annotated[
    TextBoxShape | AutoShape | Picture | Table | PassthroughShape | ChartShape | DiagramShape,
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
    source_index: int | None = None
    """For a composed slide: the `index` of the template slide it was built
    from, so `.pptx` export can clone that exact slide (background, master,
    theme, grouped art) and only swap its content. `None` for parsed slides.
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
