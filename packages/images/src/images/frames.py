"""Empty picture frames -> the talk's own images (product screenshots, photos).

Templates carry empty picture placeholders — a demo slide's device mockup, a
photo slot next to a text block. Left empty they show a blank screen or
nothing at all. When the talk's material includes images (screenshots found
in the repo archive, pictures attached directly), they go into those frames:
demo/image/solution slides first, each image used once. No network, no LLM.
"""

from __future__ import annotations

from ir_schema import Deck, Picture, Slide, TextBoxShape

# Frames smaller than this share of the slide are icon/logo slots, not a
# place for a screenshot.
_MIN_FRAME_SHARE = 0.03
# Catalogue purposes (see design_system.catalog.role_name: "demo-26") whose
# frames most want a real product image.
_PREFERRED = ("demo", "image", "solution", "features")


def _empty_frames(slide: Slide, slide_area: int) -> list[TextBoxShape]:
    return [
        s
        for s in slide.shapes
        if isinstance(s, TextBoxShape)
        and "PICTURE" in (s.placeholder_type or "")
        and not any(r.text.strip() for p in s.paragraphs for r in p.runs)
        and s.width * s.height >= _MIN_FRAME_SHARE * slide_area
    ]


def fill_empty_frames(deck: Deck, images: list[tuple[str, str]]) -> Deck:
    """Put `images` ((content type, base64 data), best first) into empty frames.

    Never mutates `deck`. Frames beyond the supply stay as they are.
    """
    if not images:
        return deck
    result = deck.model_copy(deep=True)
    slide_area = result.slide_width * result.slide_height

    def priority(position: int) -> tuple[int, int]:
        purpose = result.slides[position].layout_name.split("-")[0]
        return (0 if purpose in _PREFERRED else 1, position)

    supply = iter(images)
    for position in sorted(range(len(result.slides)), key=priority):
        slide = result.slides[position]
        for frame in _empty_frames(slide, slide_area):
            image = next(supply, None)
            if image is None:
                return result
            content_type, data = image
            picture = Picture(
                **frame.model_dump(exclude={"kind", "paragraphs"}),
                image_bytes_b64=data,
                content_type=content_type,
                image_replaced=True,
            )
            slide.shapes = [picture if s is frame else s for s in slide.shapes]
    return result
