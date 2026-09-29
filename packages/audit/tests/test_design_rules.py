"""Colour, margin, picture, layout, font and chart checks (audit.design_rules)."""

from __future__ import annotations

import base64
import io

from audit import run_checks
from audit.design_rules import contrast_ratio
from ir_schema import (
    AutoShape,
    Color,
    Deck,
    Paragraph,
    PassthroughShape,
    Picture,
    Slide,
    TextBoxShape,
    TextRun,
)
from PIL import Image

W, H = 9_144_000, 6_858_000


def _rgb(hex_color: str) -> Color:
    return Color(kind="rgb", rgb=hex_color)


def _text(
    shape_id,
    text,
    *,
    color="000000",
    size=18.0,
    left=914_400,
    top=914_400,
    width=3_000_000,
    height=600_000,
    z=1,
    bold=False,
) -> TextBoxShape:
    run = TextRun(text=text, font_name="Arial", font_size_pt=size, color=_rgb(color), bold=bold)
    return TextBoxShape(
        shape_id=shape_id,
        name=f"t{shape_id}",
        z_order=z,
        left=left,
        top=top,
        width=width,
        height=height,
        paragraphs=[Paragraph(runs=[run])],
    )


def _template() -> Deck:
    slide = Slide(
        index=0,
        layout_name="CONTENT",
        background=_rgb("FFFFFF"),
        shapes=[_text(1, "template", left=914_400, top=914_400)],
    )
    return Deck(slide_width=W, slide_height=H, slides=[slide])


def _deck(*shapes, background="FFFFFF", layout="CONTENT", source_index=None) -> Deck:
    slide = Slide(
        index=0,
        layout_name=layout,
        background=_rgb(background),
        shapes=list(shapes),
        source_index=source_index,
    )
    return Deck(slide_width=W, slide_height=H, slides=[slide])


def _found(check: str, deck: Deck, template: Deck | None = None):
    return [f for f in run_checks(deck, template or _template()) if f.check == check]


# --- contrast ---------------------------------------------------------------


def test_contrast_ratio_matches_the_wcag_extremes():
    assert round(contrast_ratio("000000", "FFFFFF"), 1) == 21.0
    assert contrast_ratio("777777", "777777") == 1.0


def test_low_contrast_text_is_flagged():
    deck = _deck(_text(2, "grey on white", color="CCCCCC", left=1_500_000))
    assert len(_found("low_contrast", deck)) == 1


def test_readable_text_is_not_flagged():
    deck = _deck(_text(2, "black on white", color="000000", left=1_500_000))
    assert _found("low_contrast", deck) == []


def test_large_text_gets_the_relaxed_threshold():
    # 3.5:1 fails for body text but passes for 28 pt headings.
    small = _deck(_text(2, "x", color="8A8A8A", size=14, left=1_500_000))
    large = _deck(_text(2, "x", color="8A8A8A", size=28, left=1_500_000))
    assert len(_found("low_contrast", small)) == 1
    assert _found("low_contrast", large) == []


def test_contrast_uses_the_fill_of_the_shape_behind():
    plate = AutoShape(
        shape_id=3,
        name="plate",
        z_order=0,
        left=1_000_000,
        top=1_000_000,
        width=4_000_000,
        height=2_000_000,
        fill_color=_rgb("000000"),
    )
    deck = _deck(
        plate, _text(2, "black on black plate", color="222222", left=1_500_000, top=1_200_000)
    )
    assert len(_found("low_contrast", deck)) == 1


def test_contrast_is_not_judged_over_a_picture():
    photo = Picture(
        shape_id=3,
        name="photo",
        z_order=0,
        left=0,
        top=0,
        width=W,
        height=H,
    )
    deck = _deck(photo, _text(2, "on a photo", color="CCCCCC", left=1_500_000))
    assert _found("low_contrast", deck) == []


def test_template_text_left_where_it_was_is_never_flagged():
    template = _template()
    template.slides[0].shapes = [_text(1, "pale by design", color="CCCCCC")]
    same_place = _deck(_text(1, "new words", color="CCCCCC"))
    assert _found("low_contrast", same_place, template) == []


# --- margins and guides -----------------------------------------------------


def test_text_pushed_into_the_edge_margin_is_flagged():
    deck = _deck(_text(2, "hugging the edge", left=30_000, top=1_500_000))
    assert len(_found("margin_violation", deck)) == 1


def test_text_far_from_the_edge_is_fine():
    deck = _deck(_text(2, "comfortable", left=1_200_000, top=1_500_000))
    assert _found("margin_violation", deck) == []


def test_moved_text_off_every_template_guide_is_flagged():
    deck = _deck(_text(2, "drifted", left=1_500_000, top=1_500_000))
    assert len(_found("misaligned", deck)) == 1


def test_moved_text_on_a_template_guide_is_fine():
    deck = _deck(_text(2, "aligned", left=914_400, top=2_500_000))
    assert _found("misaligned", deck) == []


# --- pictures ---------------------------------------------------------------


def _png_b64(width: int, height: int) -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "red").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def _picture(width, height, shown_w, shown_h, **extra) -> Picture:
    return Picture(
        shape_id=5,
        name="p",
        z_order=1,
        left=100_000,
        top=100_000,
        width=shown_w,
        height=shown_h,
        image_bytes_b64=_png_b64(width, height),
        content_type="image/png",
        image_replaced=True,
        **extra,
    )


def test_a_squeezed_picture_is_flagged():
    deck = _deck(_picture(400, 200, 2_000_000, 2_000_000))  # 2:1 shown as 1:1
    assert len(_found("image_distorted", deck)) == 1


def test_a_cropped_picture_with_matching_aspect_is_fine():
    # 400x200 cropped to its central half horizontally = 200x200, shown square.
    deck = _deck(_picture(400, 200, 2_000_000, 2_000_000, crop_left=0.25, crop_right=0.25))
    assert _found("image_distorted", deck) == []


def test_a_slide_that_is_one_picture_is_flagged():
    deck = _deck(_picture(400, 300, W, H))
    assert len(_found("slide_is_picture", deck)) == 1


def test_a_full_bleed_picture_under_text_is_fine():
    deck = _deck(_picture(400, 300, W, H), _text(2, "over the photo", left=1_500_000, z=2))
    assert _found("slide_is_picture", deck) == []


# --- layouts and fonts ------------------------------------------------------


def test_a_layout_the_template_lacks_is_flagged():
    deck = _deck(_text(2, "x", left=914_400), layout="INVENTED")
    assert len(_found("layout_not_from_template", deck)) == 1


def test_a_third_font_family_is_flagged():
    shapes = []
    for i, font in enumerate(["Arial", "Georgia", "Comic Sans MS"]):
        shape = _text(10 + i, "text", left=914_400, top=1_000_000 + i * 900_000)
        shape.paragraphs[0].runs[0].font_name = font
        shapes.append(shape)
    assert len(_found("too_many_font_families", _deck(*shapes))) == 1


# --- brand elements ---------------------------------------------------------


def test_a_logo_moved_from_its_pinned_corner_is_flagged():
    logo = Picture(
        shape_id=9, name="logo", z_order=5, left=100_000, top=100_000, width=500_000, height=300_000
    )
    template = _template()
    template.slides[0].shapes.append(logo)
    moved = logo.model_copy(update={"left": 3_000_000, "top": 3_000_000})
    deck = _deck(moved, source_index=0)
    assert len(_found("brand_element_moved", deck, template)) == 1
    assert _found("brand_element_moved", _deck(logo, source_index=0), template) == []


# --- charts -----------------------------------------------------------------

_CHART = "<c:chartSpace><c:chart>{body}</c:chart></c:chartSpace>"


def _chart(body: str, data=None) -> PassthroughShape:
    return PassthroughShape(
        shape_id=7,
        name="chart",
        z_order=1,
        left=0,
        top=0,
        width=3_000_000,
        height=2_000_000,
        original_shape_type="CHART (3)",
        raw_xml=_CHART.format(body=body),
        chart_data=data,
    )


def test_a_chart_with_too_many_series_is_flagged():
    body = "<c:ser>x</c:ser>" * 6
    assert len(_found("chart_too_many_series", _deck(_chart(body)))) == 1


def test_a_filled_chart_without_axis_titles_is_flagged():
    chart = _chart("<c:ser>a</c:ser>", data=[["", "Выручка"], ["2024", "10"]])
    assert len(_found("chart_missing_labels", _deck(chart))) == 1


def test_a_filled_chart_with_titles_and_legend_passes():
    body = (
        "<c:ser>a</c:ser><c:ser>b</c:ser>"
        "<c:catAx><c:title>Год</c:title></c:catAx><c:valAx><c:title>млн ₽</c:title></c:valAx>"
        "<c:legend></c:legend>"
    )
    chart = _chart(body, data=[["", "a", "b"], ["2024", "1", "2"]])
    assert _found("chart_missing_labels", _deck(chart)) == []


def test_the_templates_own_untouched_chart_is_left_alone():
    assert _found("chart_missing_labels", _deck(_chart("<c:ser>a</c:ser>"))) == []
