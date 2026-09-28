"""Inherited text properties: the size, font and weight text really has.

A run in a template usually doesn't state its own size or font — it inherits
them from its placeholder on the slide layout, then the master, then the
master's title/body/other text styles, and finally the deck's default text
style; fonts are often theme references ("+mj-lt" = the theme's heading
font). python-pptx reports only what the run itself says, so without this the
IR had no size for most template text: slot capacity fell back to a generic
18pt (a 44pt title looked like it held twice the text it does) and the
browser drew the text in its own default font.

`TextStyles.for_shape(shape)` returns a lookup `level -> Inherited` walking
that chain; the parser fills a run's missing size/font/bold from it.
"""

from __future__ import annotations

from dataclasses import dataclass

from pptx.opc.constants import RELATIONSHIP_TYPE as RT

_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P = "http://schemas.openxmlformats.org/presentationml/2006/main"

# Placeholder types whose text inherits the master's title style.
_TITLE_TYPES = {"title", "ctrTitle"}
# Footer-ish placeholders inherit "other" text style; everything else "body".
_OTHER_TYPES = {"dt", "ftr", "sldNum"}


@dataclass(frozen=True)
class Inherited:
    size_pt: float | None = None
    font_name: str | None = None
    bold: bool | None = None


def _level_props(lst_style, level: int) -> tuple[float | None, str | None, bool | None]:
    """(size, typeface, bold) from `<a:lvlNpPr><a:defRPr>` of a list style element."""
    if lst_style is None:
        return None, None, None
    lvl = lst_style.find(f"{{{_A}}}lvl{level + 1}pPr")
    if lvl is None:
        return None, None, None
    rpr = lvl.find(f"{{{_A}}}defRPr")
    if rpr is None:
        return None, None, None
    size = int(rpr.get("sz")) / 100 if rpr.get("sz") else None
    latin = rpr.find(f"{{{_A}}}latin")
    typeface = latin.get("typeface") if latin is not None else None
    b = rpr.get("b")
    bold = None if b is None else b in ("1", "true")
    return size, typeface or None, bold


def _tx_lst_style(element):
    """The `<a:lstStyle>` of a shape element's text body, if any."""
    body = element.find(f"{{{_P}}}txBody")
    if body is None:
        body = element.find(f"{{{_A}}}txBody")
    return body.find(f"{{{_A}}}lstStyle") if body is not None else None


def _ph_type(shape) -> str:
    return shape._element.ph.get("type") or "body"


def _matching_placeholder(container, idx: int | None, ph_type: str):
    """Same-idx placeholder in a layout/master, else the first of the same type."""
    by_type = None
    for candidate in container.placeholders:
        c_idx = candidate.placeholder_format.idx
        c_type = _ph_type(candidate)
        if idx is not None and c_idx == idx and idx != 0:
            return candidate
        same = c_type == ph_type or (c_type in _TITLE_TYPES and ph_type in _TITLE_TYPES)
        if same and by_type is None:
            by_type = candidate
    return by_type


class TextStyles:
    """Inheritance chains for one presentation (theme fonts, default styles)."""

    def __init__(self, presentation) -> None:
        self._default_style = presentation.part._element.find(f"{{{_P}}}defaultTextStyle")
        self._themes: dict[int, tuple[dict[str, str], object, object]] = {}

    def _theme(self, master) -> tuple[dict[str, str], object, object]:
        """(font refs, spDef list style, txDef list style) for a master's theme."""
        key = id(master.part)
        if key not in self._themes:
            fonts: dict[str, str] = {}
            sp_def = tx_def = None
            try:
                theme = master.part.part_related_by(RT.THEME)
                from lxml import etree

                root = etree.fromstring(theme.blob)
                for which, ref in (("majorFont", "+mj-lt"), ("minorFont", "+mn-lt")):
                    latin = root.find(f".//{{{_A}}}{which}/{{{_A}}}latin")
                    if latin is not None and latin.get("typeface"):
                        fonts[ref] = latin.get("typeface")
                sp = root.find(f".//{{{_A}}}objectDefaults/{{{_A}}}spDef")
                tx = root.find(f".//{{{_A}}}objectDefaults/{{{_A}}}txDef")
                sp_def = sp.find(f".//{{{_A}}}lstStyle") if sp is not None else None
                tx_def = tx.find(f".//{{{_A}}}lstStyle") if tx is not None else None
            except (KeyError, ValueError):
                pass
            self._themes[key] = (fonts, sp_def, tx_def)
        return self._themes[key]

    def for_shape(self, shape, slide) -> ShapeTextStyle:
        """What text in `shape` on `slide` inherits, per paragraph level."""
        master = slide.slide_layout.slide_master
        theme_fonts, sp_def, tx_def = self._theme(master)
        chain = [_tx_lst_style(shape._element)]
        if shape.is_placeholder:
            ph_type = _ph_type(shape)
            idx = shape.placeholder_format.idx
            layout_ph = _matching_placeholder(slide.slide_layout, idx, ph_type)
            if layout_ph is not None:
                chain.append(_tx_lst_style(layout_ph._element))
            master_ph = _matching_placeholder(master, None, ph_type)
            if master_ph is not None:
                chain.append(_tx_lst_style(master_ph._element))
            tx_styles = master._element.find(f"{{{_P}}}txStyles")
            if tx_styles is not None:
                name = (
                    "titleStyle"
                    if ph_type in _TITLE_TYPES
                    else "otherStyle"
                    if ph_type in _OTHER_TYPES
                    else "bodyStyle"
                )
                chain.append(tx_styles.find(f"{{{_P}}}{name}"))
        else:
            is_text_box = shape._element.find(f"{{{_P}}}nvSpPr/{{{_P}}}cNvSpPr[@txBox='1']")
            chain.append(tx_def if is_text_box is not None else sp_def)
            chain.append(self._default_style)

        return ShapeTextStyle(chain, theme_fonts)


class ShapeTextStyle:
    def __init__(self, chain: list, theme_fonts: dict[str, str]) -> None:
        self._chain = chain
        self._theme_fonts = theme_fonts

    def level(self, level: int) -> Inherited:
        size = font = bold = None
        for style in self._chain:
            s, f, b = _level_props(style, level)
            size = size if size is not None else s
            font = font if font is not None else f
            bold = bold if bold is not None else b
            if size is not None and font is not None and bold is not None:
                break
        return Inherited(size, self.font(font), bold)

    def font(self, typeface: str | None) -> str | None:
        """A typeface with theme references ("+mj-lt") resolved."""
        if typeface and typeface.startswith("+"):
            return self._theme_fonts.get(typeface)
        return typeface
