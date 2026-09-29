"""Pictograms drawn as a handful of native PowerPoint shapes.

No image files and no fonts: each icon is a few shapes on a unit square, so it
stays sharp at any size, recolours with one click in PowerPoint and is grouped
so it moves as one object. Names come from `ir_schema.ICON_NAMES`.

Only shape kinds every renderer draws are used — plain geometry and freeform
outlines. Presets like "sun" or "heart" exist in PowerPoint, but the browser
preview and other viewers skip them, and an icon that vanishes there is worse
than a slightly plainer one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ir_schema import ICON_NAMES
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

Point = tuple[float, float]


@dataclass(frozen=True)
class Part:
    """One piece of an icon: a preset ("OVAL"), a polygon, or a glyph of text."""

    kind: str  # an MSO_SHAPE name, "POLY" or "TEXT"
    x: float = 0.0
    y: float = 0.0
    w: float = 1.0
    h: float = 1.0
    rotation: float = 0.0
    role: str = "fg"  # "fg": the icon's colour; "bg": the colour behind it (a hole)
    glyph: str = ""
    points: tuple[Point, ...] = ()


def _shape(kind, x, y, w, h, rotation=0.0, role="fg") -> Part:
    return Part(kind, x, y, w, h, rotation, role)


def _poly(points: list[Point], role="fg") -> Part:
    return Part("POLY", role=role, points=tuple(points))


def _text(glyph: str, x=0.08, y=0.08, w=0.84, h=0.84) -> Part:
    return Part("TEXT", x, y, w, h, role="bg", glyph=glyph)


def _regular(cx: float, cy: float, radii: list[float], start=-90.0) -> list[Point]:
    """Vertices alternating through `radii` around (cx, cy), `start` degrees first."""
    n = len(radii)
    return [
        (
            cx + r * math.cos(math.radians(start + 360 * i / n)),
            cy + r * math.sin(math.radians(start + 360 * i / n)),
        )
        for i, r in enumerate(radii)
    ]


def _heart() -> list[Point]:
    points = []
    for i in range(48):
        t = 2 * math.pi * i / 48
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        points.append((0.5 + x / 36, 0.46 - y / 36))
    return points


_BARS = [
    _shape("RECTANGLE", 0.14, 0.58, 0.18, 0.28),
    _shape("RECTANGLE", 0.41, 0.4, 0.18, 0.46),
    _shape("RECTANGLE", 0.68, 0.16, 0.18, 0.7),
]

# Sun rays: eight thin triangles around a disc.
_RAYS = [
    _poly(
        [
            (
                0.5 + 0.34 * math.cos(math.radians(a - 9)),
                0.5 + 0.34 * math.sin(math.radians(a - 9)),
            ),
            (0.5 + 0.46 * math.cos(math.radians(a)), 0.5 + 0.46 * math.sin(math.radians(a))),
            (
                0.5 + 0.34 * math.cos(math.radians(a + 9)),
                0.5 + 0.34 * math.sin(math.radians(a + 9)),
            ),
        ]
    )
    for a in range(0, 360, 45)
]

ICONS: dict[str, list[Part]] = {
    "drop": [_shape("TEAR", 0.24, 0.3, 0.52, 0.52, -45)],
    "sun": [_shape("OVAL", 0.28, 0.28, 0.44, 0.44), *_RAYS],
    "cloud": [
        _shape("OVAL", 0.06, 0.4, 0.34, 0.34),
        _shape("OVAL", 0.28, 0.2, 0.42, 0.42),
        _shape("OVAL", 0.56, 0.38, 0.38, 0.36),
        _shape("ROUNDED_RECTANGLE", 0.2, 0.46, 0.6, 0.28),
    ],
    "leaf": [
        _shape("TEAR", 0.14, 0.14, 0.72, 0.72),
        _shape("RECTANGLE", 0.2, 0.62, 0.5, 0.05, -45, "bg"),
    ],
    "growth": [_shape("UP_ARROW", 0.24, 0.08, 0.52, 0.84)],
    "chart": _BARS,
    "money": [_shape("OVAL", 0.08, 0.08, 0.84, 0.84), _text("₽")],
    "users": [
        _shape("OVAL", 0.16, 0.14, 0.26, 0.26),
        _shape("OVAL", 0.58, 0.14, 0.26, 0.26),
        _shape("ROUND_2_SAME_RECTANGLE", 0.08, 0.46, 0.42, 0.4),
        _shape("ROUND_2_SAME_RECTANGLE", 0.5, 0.46, 0.42, 0.4),
    ],
    "gear": [
        _poly(_regular(0.5, 0.5, [0.46, 0.46, 0.34, 0.34] * 6, start=-90)),
        _shape("OVAL", 0.36, 0.36, 0.28, 0.28, 0, "bg"),
    ],
    "target": [_shape("DONUT", 0.06, 0.06, 0.88, 0.88), _shape("OVAL", 0.36, 0.36, 0.28, 0.28)],
    "idea": [
        _shape("OVAL", 0.2, 0.06, 0.6, 0.6),
        _shape("ROUNDED_RECTANGLE", 0.34, 0.62, 0.32, 0.2),
        _shape("RECTANGLE", 0.4, 0.85, 0.2, 0.07),
    ],
    "check": [_shape("OVAL", 0.08, 0.08, 0.84, 0.84), _text("✓")],
    "lock": [
        _shape("ROUND_2_SAME_RECTANGLE", 0.3, 0.1, 0.4, 0.46),
        _shape("ROUND_2_SAME_RECTANGLE", 0.4, 0.22, 0.2, 0.34, 0, "bg"),
        _shape("ROUNDED_RECTANGLE", 0.2, 0.44, 0.6, 0.46),
    ],
    "shield": [
        _poly([(0.16, 0.14), (0.5, 0.06), (0.84, 0.14), (0.84, 0.5), (0.5, 0.94), (0.16, 0.5)])
    ],
    "rocket": [
        _shape("ISOSCELES_TRIANGLE", 0.3, 0.05, 0.4, 0.55),
        _shape("RECTANGLE", 0.36, 0.5, 0.28, 0.32),
        _shape("ISOSCELES_TRIANGLE", 0.16, 0.6, 0.2, 0.28),
        _shape("ISOSCELES_TRIANGLE", 0.64, 0.6, 0.2, 0.28),
    ],
    "time": [
        _shape("OVAL", 0.08, 0.08, 0.84, 0.84),
        _shape("RECTANGLE", 0.47, 0.22, 0.06, 0.32, 0, "bg"),
        _shape("RECTANGLE", 0.47, 0.48, 0.26, 0.06, 0, "bg"),
    ],
    "home": [
        _shape("ISOSCELES_TRIANGLE", 0.06, 0.1, 0.88, 0.4),
        _shape("RECTANGLE", 0.2, 0.5, 0.6, 0.4),
        _shape("RECTANGLE", 0.43, 0.64, 0.14, 0.26, 0, "bg"),
    ],
    "globe": [
        _shape("OVAL", 0.08, 0.08, 0.84, 0.84),
        _shape("RECTANGLE", 0.08, 0.47, 0.84, 0.06, 0, "bg"),
        _shape("DONUT", 0.3, 0.08, 0.4, 0.84, 0, "bg"),
    ],
    "heart": [_poly(_heart())],
    "star": [_poly(_regular(0.5, 0.54, [0.46, 0.19] * 5))],
    "bolt": [
        _poly([(0.58, 0.04), (0.2, 0.56), (0.46, 0.56), (0.38, 0.96), (0.8, 0.4), (0.54, 0.4)])
    ],
    "phone": [
        _shape("ROUNDED_RECTANGLE", 0.3, 0.05, 0.4, 0.9),
        _shape("RECTANGLE", 0.35, 0.15, 0.3, 0.6, 0, "bg"),
    ],
    "mail": [
        _shape("RECTANGLE", 0.08, 0.22, 0.84, 0.56),
        _poly([(0.12, 0.26), (0.88, 0.26), (0.5, 0.56)], role="bg"),
    ],
    "database": [_shape("CAN", 0.2, 0.06, 0.6, 0.88)],
    "warning": [
        _shape("ISOSCELES_TRIANGLE", 0.06, 0.1, 0.88, 0.78),
        _text("!", 0.06, 0.32, 0.88, 0.56),
    ],
    "question": [_shape("OVAL", 0.08, 0.08, 0.84, 0.84), _text("?")],
}

assert set(ICONS) == set(ICON_NAMES), "every name in ir_schema.ICON_NAMES needs a drawing"


def _paint(shape, color: RGBColor) -> None:
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()


def draw_icon(shapes, name: str, left: int, top: int, size: int, fg: str, bg: str) -> None:
    """Draw icon `name` in the `size`-EMU square at (left, top).

    `shapes` is a slide's (or group's) shape collection; the icon's pieces go
    straight into it — a group inside a group is where some viewers lose shapes.
    `fg` and `bg` are 6-digit hex colours: the icon's, and the one behind it
    (used for its holes).
    """
    for part in ICONS[name]:
        color = RGBColor.from_string((fg if part.role == "fg" else bg).upper())
        if part.kind == "POLY":
            pts = [(left + int(x * size), top + int(y * size)) for x, y in part.points]
            builder = shapes.build_freeform(pts[0][0], pts[0][1])
            builder.add_line_segments(pts[1:], close=True)
            _paint(builder.convert_to_shape(), color)
            continue
        box = (
            Emu(left + int(part.x * size)),
            Emu(top + int(part.y * size)),
            Emu(max(1, int(part.w * size))),
            Emu(max(1, int(part.h * size))),
        )
        if part.kind == "TEXT":
            text = shapes.add_textbox(*box).text_frame
            text.margin_left = text.margin_right = text.margin_top = text.margin_bottom = 0
            text.vertical_anchor = MSO_ANCHOR.MIDDLE
            paragraph = text.paragraphs[0]
            paragraph.alignment = PP_ALIGN.CENTER
            run = paragraph.add_run()
            run.text = part.glyph
            run.font.bold = True
            run.font.size = Pt(max(8, size * 0.5 / 12700))
            run.font.color.rgb = color
            continue
        shape = shapes.add_shape(getattr(MSO_SHAPE, part.kind), *box)
        shape.rotation = part.rotation
        _paint(shape, color)
