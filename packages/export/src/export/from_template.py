"""Composed deck -> .pptx built *from the template file itself*.

Rebuilding slides on a blank presentation (see `export.py`) loses everything
the IR doesn't model: slide backgrounds, master/layout artwork, the theme's
fonts and colours, grouped shapes, charts. For a product whose promise is
"looks like it came from the same deck" that is fatal. So when the template
is available, each composed slide is exported by cloning the exact template
slide it was built from (`Slide.source_index`) and changing only what
composition changed:

- text shapes get their paragraphs rewritten, reusing the template
  paragraph's own formatting (pPr / rPr) so fonts, colours, bullets and
  spacing stay the template's;
- swapped photos get their image replaced; tables get their cell text;
- shapes composition removed (pruned callouts, unused slots) are deleted;
- everything else — backgrounds, pictures, groups, charts — is untouched XML.

The template's original slides are then dropped, leaving only the new deck.
"""

from __future__ import annotations

import base64
import copy
import io
import re
from pathlib import Path

from ir_schema import (
    BACKGROUND_SHAPE_ID,
    AutoShape,
    Deck,
    Paragraph,
    PassthroughShape,
    Picture,
    Slide,
    Table,
    TextBoxShape,
)
from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.oxml.ns import qn
from pptx.parts.chart import ChartPart
from pptx.parts.embeddedpackage import EmbeddedXlsxPart
from pptx.util import Pt

_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
# Relationships that belong to the source slide itself and must not be copied.
_SKIP_RELS = ("/notesSlide", "/slideLayout")


def export_from_template(deck: Deck, template_path: Path, out_path: Path) -> None:
    presentation = Presentation(str(template_path))
    originals = list(presentation.slides)

    for slide_ir in deck.slides:
        if slide_ir.source_index is None or not 0 <= slide_ir.source_index < len(originals):
            raise ValueError(f"slide {slide_ir.index} has no valid source_index")
        new_slide = _clone_slide(presentation, originals[slide_ir.source_index])
        _sync_slide(new_slide, slide_ir)
        if slide_ir.notes:
            new_slide.notes_slide.notes_text_frame.text = slide_ir.notes

    _drop_slides(presentation, originals)
    _clear_layout_prompts(presentation)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    presentation.save(str(out_path))


def _clone_slide(presentation, source):
    """A new slide at the end of the deck with `source`'s full content."""
    new_slide = presentation.slides.add_slide(source.slide_layout)
    new_tree = new_slide.shapes._spTree
    for element in list(new_tree)[2:]:  # keep nvGrpSpPr + grpSpPr
        new_tree.remove(element)

    # Re-point every relationship the source's XML uses (images, charts,
    # hyperlinks, media) from the new slide to the same targets.
    rid_map: dict[str, str] = {}
    for rid, rel in source.part.rels.items():
        if rel.reltype.endswith(_SKIP_RELS):
            continue
        if rel.is_external:
            rid_map[rid] = new_slide.part.relate_to(rel.target_ref, rel.reltype, is_external=True)
        elif rel.reltype.endswith("/chart"):
            # Own copy per cloned slide: chart data is replaced per slide, and
            # two slides cloned from one template slide must not share it.
            rid_map[rid] = new_slide.part.relate_to(_copy_chart(rel.target_part), rel.reltype)
        else:
            rid_map[rid] = new_slide.part.relate_to(rel.target_part, rel.reltype)

    source_csld = source.element.find(qn("p:cSld"))
    new_csld = new_slide.element.find(qn("p:cSld"))
    background = source_csld.find(qn("p:bg"))
    if background is not None:
        new_csld.insert(0, copy.deepcopy(background))
    for element in list(source.shapes._spTree)[2:]:
        new_tree.append(copy.deepcopy(element))

    for element in new_slide.element.iter():
        for attr, value in list(element.attrib.items()):
            if attr.startswith(f"{{{_R_NS}}}") and value in rid_map:
                element.set(attr, rid_map[value])
    return new_slide


# Placeholder types whose layout text is a real field, not a prompt.
_FIELD_PLACEHOLDERS = {"dt", "ftr", "sldNum", "hdr"}


def _clear_layout_prompts(presentation) -> None:
    """Empty the prompt text ("Образец текста") of layout placeholders.

    PowerPoint never shows a layout's prompt on a slide, but LibreOffice and
    Keynote draw it wherever the slide leaves that placeholder out or moves
    it — sample text floating over the finished deck. Formatting is kept;
    only the runs go.
    """
    for layout in presentation.slide_layouts:
        for element in layout.placeholders._spTree.iter(qn("p:sp")):
            ph = next(element.iter(qn("p:ph")), None)
            if ph is None or ph.get("type") in _FIELD_PLACEHOLDERS:
                continue
            for p in element.iter(qn("a:p")):
                for run in p.findall(qn("a:r")) + p.findall(qn("a:fld")):
                    p.remove(run)


def _copy_chart(source: ChartPart) -> ChartPart:
    """A new chart part (and embedded workbook) with `source`'s content."""
    package = source.package
    chart = ChartPart.load(
        package.next_partname(ChartPart.partname_template),
        source.content_type,
        package,
        source.blob,
    )
    rid_map: dict[str, str] = {}
    for rid, rel in source.rels.items():
        if rel.is_external:
            rid_map[rid] = chart.relate_to(rel.target_ref, rel.reltype, is_external=True)
        elif rel.reltype.endswith("/package"):
            workbook = EmbeddedXlsxPart.new(rel.target_part.blob, package)
            rid_map[rid] = chart.relate_to(workbook, rel.reltype)
        else:
            rid_map[rid] = chart.relate_to(rel.target_part, rel.reltype)
    for element in chart._element.iter():
        for attr, value in list(element.attrib.items()):
            if attr.startswith(f"{{{_R_NS}}}") and value in rid_map:
                element.set(attr, rid_map[value])
    return chart


def _drop_slides(presentation, slides) -> None:
    id_list = presentation.slides._sldIdLst
    drop = {slide.part for slide in slides}
    for sld_id in list(id_list):
        rid = sld_id.get(qn("r:id"))
        if presentation.part.related_part(rid) in drop:
            presentation.part.drop_rel(rid)
            id_list.remove(sld_id)


def _shape_elements(slide) -> dict[int, etree._Element]:
    """Top-level shape elements by their `cNvPr` id (= IR `shape_id`)."""
    found = {}
    for element in list(slide.shapes._spTree)[2:]:
        c_nv_pr = next(element.iter(qn("p:cNvPr")), None)
        if c_nv_pr is not None:
            found[int(c_nv_pr.get("id"))] = element
    return found


_SHAPE_TAGS = {qn(t) for t in ("p:sp", "p:pic", "p:grpSp", "p:graphicFrame", "p:cxnSp")}


def _all_shape_elements(slide) -> dict[int, etree._Element]:
    """Every shape element at any depth (inside groups too) by `cNvPr` id."""
    found = {}
    for element in slide.shapes._spTree.iter(*_SHAPE_TAGS):
        c_nv_pr = next(element.iter(qn("p:cNvPr")), None)
        if c_nv_pr is not None:
            found.setdefault(int(c_nv_pr.get("id")), element)
    return found


def _is_top_level(slide, element: etree._Element) -> bool:
    return element.getparent() is slide.shapes._spTree


def _sync_slide(slide, slide_ir: Slide) -> None:
    kept = {shape.shape_id for shape in slide_ir.shapes}
    # Only slide-level shapes are ever dropped: a group's members the IR
    # doesn't list are its decoration, carried by the group itself.
    for shape_id, element in _shape_elements(slide).items():
        if shape_id not in kept:
            element.getparent().remove(element)
    elements = _all_shape_elements(slide)
    # A group member holding text that composition dropped (an unused label,
    # a surplus card field) can't be removed from its group without upsetting
    # the group's layout — its text is blanked instead. Every text-bearing
    # member is in the IR (parser lists them all), so absent means dropped.
    for shape_id, element in elements.items():
        if shape_id in kept or element.tag != qn("p:sp") or _is_top_level(slide, element):
            continue
        tx_body = element.find(qn("p:txBody"))
        if tx_body is not None and _text_of(tx_body):
            _write_paragraphs(tx_body, [])

    _sync_geometry(slide, slide_ir)
    for shape_ir in slide_ir.shapes:
        if shape_ir.shape_id == BACKGROUND_SHAPE_ID:
            background = slide.element.find(f"{qn('p:cSld')}/{qn('p:bg')}")
            if background is not None and isinstance(shape_ir, Picture) and shape_ir.image_replaced:
                _replace_picture(slide, background, shape_ir)
            continue
        element = elements.get(shape_ir.shape_id)
        if element is None:
            continue
        if isinstance(shape_ir, (TextBoxShape, AutoShape)):
            tx_body = element.find(qn("p:txBody"))
            # Untouched text (step numbers, labels composition kept) stays
            # byte-for-byte the template's — including per-run formatting a
            # rewrite from one prototype would flatten.
            if tx_body is not None and _text_of(tx_body) != _ir_text(shape_ir.paragraphs):
                _write_paragraphs(tx_body, shape_ir.paragraphs)
        elif isinstance(shape_ir, Picture) and next(element.iter(qn("a:blip")), None) is not None:
            # A picture, or a shape filled with one: swap the image itself,
            # keeping the frame's shape, crop box and effects.
            if shape_ir.image_replaced or shape_ir.attribution_text:
                _replace_picture(slide, element, shape_ir)
        elif isinstance(shape_ir, Picture) and element.tag == qn("p:sp"):
            _fill_placeholder(slide, shape_ir)
        elif isinstance(shape_ir, Table):
            _write_table(element, shape_ir)
        elif isinstance(shape_ir, PassthroughShape) and shape_ir.chart_data:
            _write_chart(slide, shape_ir)


def _sync_geometry(slide, slide_ir: Slide) -> None:
    """Apply position/size changes composition made (e.g. a plate grown to
    fit its title, a title box widened). python-pptx reads a placeholder's
    inherited geometry and writes an own `a:xfrm` only when one is needed."""
    by_id = {s.shape_id: s for s in slide_ir.shapes}
    for shape in slide.shapes:
        shape_ir = by_id.get(shape.shape_id)
        if shape_ir is None:
            continue
        for attr in ("left", "top", "width", "height"):
            value = getattr(shape_ir, attr)
            current = getattr(shape, attr)
            if current is not None and int(current) != value:
                setattr(shape, attr, value)


def _text_of(tx_body: etree._Element) -> str:
    return "\n".join(
        "".join(t.text or "" for t in p.iter(qn("a:t"))) for p in tx_body.findall(qn("a:p"))
    ).strip()


def _ir_text(paragraphs: list[Paragraph]) -> str:
    return "\n".join("".join(r.text for r in p.runs) for p in paragraphs).strip()


def _write_paragraphs(tx_body: etree._Element, paragraphs: list[Paragraph]) -> None:
    """Replace a text body's paragraphs, keeping the template's formatting.

    The first existing paragraph is the style prototype: its paragraph
    properties and its first run's run properties are reused for every new
    paragraph, so an empty template placeholder keeps inheriting the layout's
    styles and a styled text box keeps its own. Only an explicit size from
    composition (shrink-to-fit) and the paragraph level override it.
    """
    old = tx_body.findall(qn("a:p"))
    prototype = old[0] if old else etree.SubElement(tx_body, qn("a:p"))
    proto_ppr = prototype.find(qn("a:pPr"))
    proto_end = prototype.find(qn("a:endParaRPr"))
    proto_rpr = next(prototype.iter(qn("a:rPr")), None)
    if proto_rpr is None and proto_end is not None:
        # An empty template slot has no runs, but its end-of-paragraph
        # properties are what the author set for text typed into it (seen
        # live: accent5 on the slide vs the layout prompt's pale accent2) —
        # the best prototype there is.
        proto_rpr = copy.deepcopy(proto_end)
        proto_rpr.tag = qn("a:rPr")
    for p in old:
        tx_body.remove(p)

    if not paragraphs:
        empty = etree.SubElement(tx_body, qn("a:p"))
        if proto_end is not None:
            empty.append(copy.deepcopy(proto_end))
        return

    for paragraph_ir in paragraphs:
        p = etree.SubElement(tx_body, qn("a:p"))
        if proto_ppr is not None:
            ppr = copy.deepcopy(proto_ppr)
            p.append(ppr)
        if paragraph_ir.level:
            ppr = p.find(qn("a:pPr"))
            if ppr is None:
                ppr = etree.SubElement(p, qn("a:pPr"))
            ppr.set("lvl", str(paragraph_ir.level))
        for run_ir in paragraph_ir.runs:
            r = etree.SubElement(p, qn("a:r"))
            rpr = copy.deepcopy(proto_rpr) if proto_rpr is not None else None
            if run_ir.font_size_pt is not None:
                if rpr is None:
                    rpr = etree.Element(qn("a:rPr"))
                rpr.set("sz", str(round(Pt(run_ir.font_size_pt).pt * 100)))
            if rpr is not None:
                r.append(rpr)
            t = etree.SubElement(r, qn("a:t"))
            t.text = run_ir.text
        if proto_end is not None:
            p.append(copy.deepcopy(proto_end))


def _fill_placeholder(slide, shape_ir: Picture) -> None:
    """An empty picture placeholder composition gave an image: insert it,
    cropped to the frame (python-pptx does the fill-crop)."""
    shape = next((s for s in slide.placeholders if s.shape_id == shape_ir.shape_id), None)
    if shape is None or not hasattr(shape, "insert_picture") or not shape_ir.image_bytes_b64:
        return
    shape.insert_picture(io.BytesIO(base64.b64decode(shape_ir.image_bytes_b64)))


def _replace_picture(slide, element: etree._Element, shape_ir: Picture) -> None:
    blip = next(element.iter(qn("a:blip")), None)
    if blip is None or not shape_ir.image_bytes_b64:
        return
    image = io.BytesIO(base64.b64decode(shape_ir.image_bytes_b64))
    _, rid = slide.part.get_or_add_image_part(image)
    blip.set(qn("r:embed"), rid)
    # The template's crop was framed for its own image.
    for src_rect in element.iter(qn("a:srcRect")):
        src_rect.getparent().remove(src_rect)


def _number(cell: str) -> float:
    match = re.search(r"[-+]?\d+(?:[.,]\d+)?", cell.replace("\u00a0", "").replace(" ", ""))
    return float(match.group().replace(",", ".")) if match else 0.0


def _write_chart(slide, shape_ir: PassthroughShape) -> None:
    """Replace a template chart's sample series with the composed data.

    The chart keeps its type, colours and formatting; only categories,
    series names and values change.
    """
    frame = next((s for s in slide.shapes if s.shape_id == shape_ir.shape_id), None)
    if frame is None or not getattr(frame, "has_chart", False):
        return
    header, *rows = shape_ir.chart_data
    data = CategoryChartData()
    data.categories = [row[0] for row in rows]
    for col, name in enumerate(header[1:], start=1):
        data.add_series(name, [_number(row[col]) for row in rows])
    frame.chart.replace_data(data)


def _write_table(element: etree._Element, shape_ir: Table) -> None:
    tbl = next(element.iter(qn("a:tbl")), None)
    if tbl is None or not shape_ir.rows:
        return
    rows = tbl.findall(qn("a:tr"))
    grid = tbl.find(qn("a:tblGrid"))
    cols = grid.findall(qn("a:gridCol")) if grid is not None else []
    want_rows, want_cols = len(shape_ir.rows), max(len(r) for r in shape_ir.rows)

    # Columns: trim or repeat the last one, in the grid and every row.
    if cols and want_cols != len(cols):
        for tr in [grid, *rows]:
            cells = tr.findall(qn("a:gridCol")) if tr is grid else tr.findall(qn("a:tc"))
            for extra in cells[want_cols:]:
                tr.remove(extra)
            for _ in range(want_cols - len(cells)):
                tr.append(copy.deepcopy(cells[-1]))
    # Rows: trim or repeat the last one.
    for extra in rows[want_rows:]:
        tbl.remove(extra)
    for _ in range(want_rows - len(rows)):
        tbl.append(copy.deepcopy(rows[-1]))

    for tr, row_ir in zip(tbl.findall(qn("a:tr")), shape_ir.rows, strict=False):
        for tc, cell_ir in zip(tr.findall(qn("a:tc")), row_ir, strict=False):
            tx_body = tc.find(qn("a:txBody"))
            if tx_body is not None:
                _write_paragraphs(tx_body, cell_ir.paragraphs)
