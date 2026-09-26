"""uv run pytest packages/export"""

from export.export import export_pptx
from lxml import etree
from parser.parser import parse
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn
from pptx.util import Inches


def _template(path):
    prs = Presentation()
    blank = prs.slide_layouts[6]
    for label in ("Cover", "Body"):
        slide = prs.slides.add_slide(blank)
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = RGBColor(0x44, 0x11, 0x88)
        keep = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
        keep.text_frame.text = f"{label} heading"
        keep.text_frame.paragraphs[0].runs[0].font.size = Inches(0.4)
        drop = slide.shapes.add_textbox(Inches(1), Inches(3), Inches(4), Inches(1))
        drop.text_frame.text = "Имя Фамилия"
    prs.save(str(path))


def test_export_clones_source_slide_keeps_design_and_swaps_content(tmp_path):
    template = tmp_path / "t.pptx"
    _template(template)
    deck = parse(template)

    composed = deck.model_copy(deep=True)
    slide = composed.slides[1].model_copy(deep=True)  # built from template slide #2
    slide.index, slide.source_index, slide.notes = 0, 1, "Говорим"
    heading, sample = slide.shapes
    heading.paragraphs[0].runs[0].text = "Новый заголовок"
    slide.shapes = [heading]  # composition removed the sample text box
    composed.slides = [slide]

    out = tmp_path / "out.pptx"
    export_pptx(composed, out, template_path=template)

    result = Presentation(str(out))
    assert len(result.slides) == 1  # template's own slides dropped
    new = result.slides[0]
    texts = [s.text_frame.text for s in new.shapes if s.has_text_frame]
    assert texts == ["Новый заголовок"]
    # Template formatting (run size) and the slide background survive.
    run = new.shapes[0].text_frame.paragraphs[0].runs[0]
    assert run.font.size == Inches(0.4)
    assert new.element.find(qn("p:cSld")).find(qn("p:bg")) is not None
    assert new.notes_slide.notes_text_frame.text == "Говорим"


def test_empty_paragraph_keeps_its_end_font_size(tmp_path):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    p = box.text_frame.paragraphs[0]._p
    end = etree.SubElement(p, qn("a:endParaRPr"))
    end.set("sz", "4000")
    path = tmp_path / "e.pptx"
    prs.save(str(path))

    shape = parse(path).slides[0].shapes[0]

    run = shape.paragraphs[0].runs[0]
    assert (run.text, run.font_size_pt) == ("", 40.0)
