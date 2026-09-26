"""Recreate 3 .pptx templates approximating Behance pitch-deck references.

Not real downloads of those decks (Behance galleries are image showcases,
no editable source file is published) — these are hand-built python-pptx
approximations of each one's color palette, typography, and slide patterns,
built by eye from the gallery screenshots. Run once to (re)populate
evals/templates/ with all three:

    uv run python evals/generate_behance_templates.py

References:
- savant:   https://www.behance.net/gallery/250361117/ (dark futuristic AI)
- pawvera:  https://www.behance.net/gallery/243432333/ (warm pet-insurance)
- parusim:  https://www.behance.net/gallery/198541629/ (bold vintage-coral)
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

OUT_DIR = Path(__file__).resolve().parent / "templates"
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


def _new_deck() -> Presentation:
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    return prs


def _layout(prs: Presentation, name: str):
    for layout in prs.slide_layouts:
        if layout.name == name:
            return layout
    raise KeyError(name)


def _bg(slide, hex_color: str) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor.from_string(hex_color)


def _style(run, *, font: str, size: int, bold: bool = False, color: str = "FFFFFF") -> None:
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)


def _set_text(shape, text: str, *, font: str, size: int, bold: bool = False, color: str = "FFFFFF", align=None):
    tf = shape.text_frame
    tf.text = text
    p = tf.paragraphs[0]
    if align is not None:
        p.alignment = align
    for run in p.runs:
        _style(run, font=font, size=size, bold=bold, color=color)


def _bullets(shape, items: list[str], *, font: str, size: int, color: str, bold: bool = False) -> None:
    tf = shape.text_frame
    tf.text = items[0]
    for run in tf.paragraphs[0].runs:
        _style(run, font=font, size=size, bold=bold, color=color)
    for item in items[1:]:
        p = tf.add_paragraph()
        p.text = item
        run = p.add_run() if not p.runs else p.runs[0]
        # add_paragraph with .text set already creates the run; re-fetch:
        for run in p.runs:
            _style(run, font=font, size=size, bold=bold, color=color)


def _rect(slide, x, y, w, h, *, fill: str | None, line: str | None = None, shape=MSO_SHAPE.RECTANGLE):
    sp = slide.shapes.add_shape(shape, x, y, w, h)
    if fill is None:
        sp.fill.background()
    else:
        sp.fill.solid()
        sp.fill.fore_color.rgb = RGBColor.from_string(fill)
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = RGBColor.from_string(line)
        sp.line.width = Pt(1)
    sp.shadow.inherit = False
    return sp


def _pill(slide, x, y, text: str, *, fill: str, text_color: str, font: str, w=Inches(1.7), h=Inches(0.4)):
    sp = _rect(slide, x, y, w, h, fill=fill, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    tf = sp.text_frame
    tf.margin_left = Pt(4)
    tf.margin_right = Pt(4)
    tf.text = text
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    for run in p.runs:
        _style(run, font=font, size=11, bold=True, color=text_color)
    return sp


# ---------------------------------------------------------------------------
# 1. Savant — dark futuristic AI (navy/white/light-blue, geometric sans)
# ---------------------------------------------------------------------------

SAVANT_BG = "050412"
SAVANT_BG_LIGHT = "FFFFFF"
SAVANT_ACCENT = "8DCCFF"
SAVANT_MUTED = "A3C5CE"
SAVANT_FONT = "Century Gothic"


def build_savant() -> Presentation:
    prs = _new_deck()

    # Title slide — dark bg, oversized headline, accent kicker, corner brackets.
    slide = prs.slides.add_slide(_layout(prs, "Title Slide"))
    _bg(slide, SAVANT_BG)
    title, subtitle = slide.placeholders[0], slide.placeholders[1]
    title.left, title.top, title.width, title.height = Inches(0.9), Inches(2.7), Inches(10), Inches(1.6)
    _set_text(title, "Intelligence That Adapts", font=SAVANT_FONT, size=48, bold=True, color=SAVANT_BG_LIGHT)
    subtitle.left, subtitle.top, subtitle.width, subtitle.height = Inches(0.9), Inches(4.2), Inches(8), Inches(0.8)
    _set_text(subtitle, "Smarter workflows, faster decisions, seamless productivity powered by AI.",
              font=SAVANT_FONT, size=16, color=SAVANT_MUTED)
    _rect(slide, Inches(0.4), Inches(0.4), Inches(0.5), Pt(2), fill=SAVANT_ACCENT)
    _rect(slide, Inches(0.4), Inches(0.4), Pt(2), Inches(0.5), fill=SAVANT_ACCENT)
    _rect(slide, Inches(12.4), Inches(6.6), Inches(0.5), Pt(2), fill=SAVANT_ACCENT)
    _rect(slide, Inches(12.88), Inches(6.6), Pt(2), Inches(0.5), fill=SAVANT_ACCENT)
    _pill(slide, Inches(11.0), Inches(0.5), "PITCH · DECK", fill=SAVANT_BG, text_color=SAVANT_MUTED, font=SAVANT_FONT, w=Inches(1.9))

    # Title and Content — dark bg, kicker + title + body bullets.
    slide = prs.slides.add_slide(_layout(prs, "Title and Content"))
    _bg(slide, SAVANT_BG)
    title, body = slide.placeholders[0], slide.placeholders[1]
    title.left, title.top, title.width, title.height = Inches(0.9), Inches(1.2), Inches(9), Inches(1.2)
    _set_text(title, "AI Core", font=SAVANT_FONT, size=40, bold=True, color=SAVANT_BG_LIGHT)
    body.left, body.top, body.width, body.height = Inches(0.9), Inches(2.6), Inches(6.5), Inches(3.5)
    _bullets(body, [
        "Advanced intelligence designed to understand, learn, and adapt",
        "Delivering accurate insights through continuous learning",
        "Intelligent processing across diverse digital environments",
    ], font=SAVANT_FONT, size=16, color=SAVANT_MUTED)
    _rect(slide, Inches(0.4), Inches(0.4), Inches(0.5), Pt(2), fill=SAVANT_ACCENT)
    _rect(slide, Inches(0.4), Inches(0.4), Pt(2), Inches(0.5), fill=SAVANT_ACCENT)

    # Two Content — light bg, two parallel columns (cards).
    slide = prs.slides.add_slide(_layout(prs, "Two Content"))
    _bg(slide, SAVANT_BG_LIGHT)
    title = slide.placeholders[0]
    title.left, title.top, title.width, title.height = Inches(0.9), Inches(0.6), Inches(10), Inches(1.0)
    _set_text(title, "Challenges in Modern Workflow", font=SAVANT_FONT, size=34, bold=True, color=SAVANT_BG)
    left, right = slide.placeholders[1], slide.placeholders[2]
    left.left, left.top, left.width, left.height = Inches(0.9), Inches(2.0), Inches(5.4), Inches(4.5)
    _set_text(left, "Data Complexity", font=SAVANT_FONT, size=24, bold=True, color=SAVANT_BG)
    right.left, right.top, right.width, right.height = Inches(6.9), Inches(2.0), Inches(5.4), Inches(4.5)
    _bullets(right, [
        "Organizations need faster, smarter workflows",
        "317,420 data points processed daily",
    ], font=SAVANT_FONT, size=16, color=SAVANT_MUTED)
    circ = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(9.5), Inches(0.6), Inches(3), Inches(3))
    circ.fill.background()
    circ.line.color.rgb = RGBColor.from_string(SAVANT_ACCENT)
    circ.line.width = Pt(1)
    circ.line.dash_style = None
    circ.shadow.inherit = False

    # Comparison — dark bg, big stat + label pairs (used as a stat-pair slide).
    slide = prs.slides.add_slide(_layout(prs, "Comparison"))
    _bg(slide, SAVANT_BG)
    title = slide.placeholders[0]
    title.left, title.top, title.width, title.height = Inches(0.9), Inches(0.6), Inches(10), Inches(0.9)
    _set_text(title, "Results That Compound", font=SAVANT_FONT, size=32, bold=True, color=SAVANT_BG_LIGHT)
    stat1_label, stat1_val = slide.placeholders[1], slide.placeholders[2]
    stat2_label, stat2_val = slide.placeholders[3], slide.placeholders[4]
    stat1_val.left, stat1_val.top, stat1_val.width, stat1_val.height = Inches(0.9), Inches(2.0), Inches(5.4), Inches(1.2)
    _set_text(stat1_val, "87+", font=SAVANT_FONT, size=54, bold=True, color=SAVANT_ACCENT)
    stat1_label.left, stat1_label.top, stat1_label.width, stat1_label.height = Inches(0.9), Inches(3.3), Inches(5.4), Inches(0.8)
    _set_text(stat1_label, "Workflows automated per client", font=SAVANT_FONT, size=14, color=SAVANT_MUTED)
    stat2_val.left, stat2_val.top, stat2_val.width, stat2_val.height = Inches(6.9), Inches(2.0), Inches(5.4), Inches(1.2)
    _set_text(stat2_val, "3.4x", font=SAVANT_FONT, size=54, bold=True, color=SAVANT_ACCENT)
    stat2_label.left, stat2_label.top, stat2_label.width, stat2_label.height = Inches(6.9), Inches(3.3), Inches(5.4), Inches(0.8)
    _set_text(stat2_label, "Faster decision cycles", font=SAVANT_FONT, size=14, color=SAVANT_MUTED)

    # Title Only — light bg, single closing statement.
    slide = prs.slides.add_slide(_layout(prs, "Title Only"))
    _bg(slide, SAVANT_BG_LIGHT)
    title = slide.placeholders[0]
    title.left, title.top, title.width, title.height = Inches(1.2), Inches(3.0), Inches(11), Inches(1.5)
    _set_text(title, "Beyond Human Thinking — Savant Intelligence", font=SAVANT_FONT, size=36, bold=True, color=SAVANT_BG)

    return prs


# ---------------------------------------------------------------------------
# 2. Pawvera — warm pet-insurance (dark green/cream/terracotta, rounded sans)
# ---------------------------------------------------------------------------

PAW_DARK = "1B3A2E"
PAW_CREAM = "F3ECDF"
PAW_ACCENT = "C97B4A"
PAW_FONT = "Century Gothic"


def build_pawvera() -> Presentation:
    prs = _new_deck()

    slide = prs.slides.add_slide(_layout(prs, "Title Slide"))
    _bg(slide, PAW_DARK)
    title, subtitle = slide.placeholders[0], slide.placeholders[1]
    _pill(slide, Inches(0.9), Inches(1.6), "ABOUT PAWVERA PET INSURANCE", fill=PAW_ACCENT, text_color=PAW_CREAM, font=PAW_FONT, w=Inches(3.6))
    title.left, title.top, title.width, title.height = Inches(0.9), Inches(2.3), Inches(10.5), Inches(1.8)
    _set_text(title, "Pawvera simplifies pet protection with clear pricing", font=PAW_FONT, size=36, bold=True, color=PAW_CREAM)
    subtitle.left, subtitle.top, subtitle.width, subtitle.height = Inches(0.9), Inches(4.3), Inches(9), Inches(0.8)
    _set_text(subtitle, "No jargon, no restrictions — just peace of mind for pet owners.", font=PAW_FONT, size=16, color=PAW_ACCENT)

    slide = prs.slides.add_slide(_layout(prs, "Title and Content"))
    _bg(slide, PAW_CREAM)
    title, body = slide.placeholders[0], slide.placeholders[1]
    _pill(slide, Inches(0.9), Inches(0.6), "THE PROBLEM", fill=PAW_DARK, text_color=PAW_CREAM, font=PAW_FONT, w=Inches(1.8))
    title.left, title.top, title.width, title.height = Inches(0.9), Inches(1.3), Inches(9), Inches(1.4)
    _set_text(title, "Skyrocketing pet medical bills with no safety net", font=PAW_FONT, size=32, bold=True, color=PAW_DARK)
    body.left, body.top, body.width, body.height = Inches(0.9), Inches(2.9), Inches(6.5), Inches(3.5)
    _bullets(body, [
        "1 in 3 pets require emergency vet care each year",
        "-75% of emergency vet visits cost over $1,500",
        "-97% of pets aren't insured in the U.S.",
        "-65% of pet owners delay or avoid treatment due to cost",
    ], font=PAW_FONT, size=15, color=PAW_DARK)

    slide = prs.slides.add_slide(_layout(prs, "Two Content"))
    _bg(slide, PAW_DARK)
    title = slide.placeholders[0]
    title.left, title.top, title.width, title.height = Inches(0.9), Inches(0.6), Inches(10), Inches(0.9)
    _set_text(title, "Why Pawvera works", font=PAW_FONT, size=32, bold=True, color=PAW_CREAM)
    left, right = slide.placeholders[1], slide.placeholders[2]
    left.left, left.top, left.width, left.height = Inches(0.9), Inches(2.0), Inches(5.4), Inches(4.5)
    _bullets(left, ["No Hard Trade-Offs", "Care decisions without financial fear"], font=PAW_FONT, size=16, bold=True, color=PAW_CREAM)
    right.left, right.top, right.width, right.height = Inches(6.9), Inches(2.0), Inches(5.4), Inches(4.5)
    _bullets(right, ["Fast, Reliable Payouts", "95% of claims reimbursed within 2 days"], font=PAW_FONT, size=16, bold=True, color=PAW_CREAM)
    for x in (Inches(0.9), Inches(6.9)):
        _rect(slide, x, Inches(1.85), Inches(5.4), Inches(2.2), fill=None, line=PAW_ACCENT)

    # Comparison — cream bg + a real comparison table (competitor grid).
    slide = prs.slides.add_slide(_layout(prs, "Comparison"))
    _bg(slide, PAW_CREAM)
    for ph in list(slide.placeholders):
        if ph.placeholder_format.idx != 0:
            ph._element.getparent().remove(ph._element)
    title = slide.placeholders[0]
    title.left, title.top, title.width, title.height = Inches(0.9), Inches(0.6), Inches(9), Inches(1.0)
    _set_text(title, "Why we're better than the alternatives", font=PAW_FONT, size=30, bold=True, color=PAW_DARK)
    rows, cols = 4, 4
    table_shape = slide.shapes.add_table(rows, cols, Inches(0.9), Inches(2.0), Inches(11.5), Inches(3.6))
    table = table_shape.table
    headers = ["Feature", "Pawvera", "Petisure", "FurGuard"]
    for c, text in enumerate(headers):
        cell = table.cell(0, c)
        cell.text = text
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor.from_string(PAW_DARK)
        for run in cell.text_frame.paragraphs[0].runs:
            _style(run, font=PAW_FONT, size=13, bold=True, color=PAW_CREAM)
    data = [
        ["Flexible Wellness Plan", "Yes", "No", "No"],
        ["Extra Visits for Senior Pets", "Yes", "No", "Yes"],
        ["Dental Illness Coverage", "Yes", "No", "No"],
        ["24/7 Pet Telehealth", "Yes", "No", "Yes"],
    ][: rows - 1]
    for r, row in enumerate(data, start=1):
        for c, text in enumerate(row):
            cell = table.cell(r, c)
            cell.text = text
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor.from_string("FFFFFF" if c else PAW_CREAM)
            for run in cell.text_frame.paragraphs[0].runs:
                _style(run, font=PAW_FONT, size=12, bold=(c == 0), color=PAW_DARK)

    slide = prs.slides.add_slide(_layout(prs, "Title Only"))
    _bg(slide, PAW_DARK)
    title = slide.placeholders[0]
    title.left, title.top, title.width, title.height = Inches(1.2), Inches(3.0), Inches(11), Inches(1.5)
    _set_text(title, "Peace of mind for every pet owner", font=PAW_FONT, size=36, bold=True, color=PAW_CREAM)

    return prs


# ---------------------------------------------------------------------------
# 3. Парусим по-алому — bold vintage-coral collage (coral/black/cream)
# ---------------------------------------------------------------------------

PAR_CORAL = "E3502E"
PAR_BLACK = "1A1A1A"
PAR_CREAM = "F3ECDD"
PAR_HEAD_FONT = "Impact"
PAR_BODY_FONT = "Georgia"


def build_parusim() -> Presentation:
    prs = _new_deck()

    slide = prs.slides.add_slide(_layout(prs, "Title Slide"))
    _bg(slide, PAR_CORAL)
    title, subtitle = slide.placeholders[0], slide.placeholders[1]
    title.left, title.top, title.width, title.height = Inches(0.9), Inches(1.8), Inches(10.5), Inches(2.2)
    _set_text(title, "Парусим по-алому", font=PAR_HEAD_FONT, size=54, bold=True, color=PAR_BLACK)
    subtitle.left, subtitle.top, subtitle.width, subtitle.height = Inches(0.9), Inches(4.0), Inches(9), Inches(0.7)
    _set_text(subtitle, "Интерактивное городское приключение", font=PAR_BODY_FONT, size=18, color=PAR_BLACK)
    tags = ["Длительность — 2-4 часа", "Локация — Санкт-Петербург", "Участников — 50-200"]
    for i, tag in enumerate(tags):
        _pill(slide, Inches(0.9 + i * 2.9), Inches(5.0), tag, fill=PAR_CREAM, text_color=PAR_BLACK, font=PAR_BODY_FONT, w=Inches(2.7))

    slide = prs.slides.add_slide(_layout(prs, "Section Header"))
    _bg(slide, PAR_CREAM)
    title, body = slide.placeholders[0], slide.placeholders[1]
    title.left, title.top, title.width, title.height = Inches(0.9), Inches(1.2), Inches(10.5), Inches(1.4)
    _set_text(title, "В путь!", font=PAR_HEAD_FONT, size=44, bold=True, color=PAR_CORAL)
    body.left, body.top, body.width, body.height = Inches(0.9), Inches(2.8), Inches(8.5), Inches(2.5)
    _set_text(body, "Забудьте об обычных экскурсиях — «Парусим по-алому» открывает город с новой стороны.",
              font=PAR_BODY_FONT, size=18, color=PAR_BLACK)
    _rect(slide, Inches(0.9), Inches(2.6), Inches(4), Pt(3), fill=PAR_CORAL)

    slide = prs.slides.add_slide(_layout(prs, "Two Content"))
    _bg(slide, PAR_CORAL)
    title = slide.placeholders[0]
    title.left, title.top, title.width, title.height = Inches(0.9), Inches(0.6), Inches(10), Inches(1.0)
    _set_text(title, "А куда идти?", font=PAR_HEAD_FONT, size=40, bold=True, color=PAR_BLACK)
    left, right = slide.placeholders[1], slide.placeholders[2]
    left.left, left.top, left.width, left.height = Inches(0.9), Inches(2.0), Inches(5.4), Inches(4.5)
    _bullets(left, ["01. Гуляем по Питеру и ищем локации", "02. Пробуем себя в квизе"], font=PAR_BODY_FONT, size=16, bold=True, color=PAR_BLACK)
    right.left, right.top, right.width, right.height = Inches(6.9), Inches(2.0), Inches(5.4), Inches(4.5)
    _bullets(right, ["03. Встречаемся на точках", "04. Собираемся на гранд-финал"], font=PAR_BODY_FONT, size=16, bold=True, color=PAR_BLACK)

    slide = prs.slides.add_slide(_layout(prs, "Title and Content"))
    _bg(slide, PAR_CREAM)
    title, body = slide.placeholders[0], slide.placeholders[1]
    title.left, title.top, title.width, title.height = Inches(0.9), Inches(1.0), Inches(10), Inches(1.2)
    _set_text(title, "Шрифты и стиль", font=PAR_HEAD_FONT, size=36, bold=True, color=PAR_CORAL)
    body.left, body.top, body.width, body.height = Inches(0.9), Inches(2.5), Inches(8), Inches(3)
    _bullets(body, [
        "Rostov для заголовков — плакатный, дерзкий",
        "Involve для основного текста — читаемый, нейтральный",
        "Коллаж из гравюр и комикс-акцентов",
    ], font=PAR_BODY_FONT, size=16, color=PAR_BLACK)

    slide = prs.slides.add_slide(_layout(prs, "Title Only"))
    _bg(slide, PAR_BLACK)
    title = slide.placeholders[0]
    title.left, title.top, title.width, title.height = Inches(1.2), Inches(3.0), Inches(11), Inches(1.5)
    _set_text(title, "Собираемся на гранд-финал", font=PAR_HEAD_FONT, size=44, bold=True, color=PAR_CORAL)

    return prs


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, builder in (
        ("savant", build_savant),
        ("pawvera", build_pawvera),
        ("parusim-po-alomu", build_parusim),
    ):
        prs = builder()
        dest = OUT_DIR / f"{name}.pptx"
        prs.save(dest)
        print(f"wrote {dest}")


if __name__ == "__main__":
    main()
