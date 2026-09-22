"""Composed deck -> real, on-topic photos in place of template placeholder images.

No LLM call here — the topic query (`SlideContent.image_brief`) was already
written by `skills/slide-content`; this only turns that brief into a real
photo via Unsplash search (see `client.py`) and swaps it into the deck's own
`Picture` shapes. Kept as its own step, called after `layout.compose_deck`
rather than folded into it, so composition itself stays what its own
docstring promises: pure, deterministic, network-free Python.
"""

from __future__ import annotations

import base64

from generator.content import DeckContent
from ir_schema import Deck, Picture

from images.client import UnsplashClient


def replace_pictures_with_photos(
    deck: Deck, deck_content: DeckContent, client: UnsplashClient
) -> Deck:
    """Swap in a real Unsplash photo for every slide with an `image_brief`.

    Only slides where content generation actually asked for on-topic imagery
    (`SlideContent.image_brief` is set — meaning that slide's pattern has a
    picture shape and the writer judged it needs one) are touched; every
    other slide keeps whatever image the template originally had. All
    `Picture` shapes on a matching slide get the *same* found photo — a
    slide's picture shapes are typically one image split across crop
    regions or a single hero image, not independently-themed pictures, and
    content generation writes one brief per slide, not one per shape.

    Never mutates `deck` (returns a deep copy, matching `compose_deck`'s own
    no-mutation contract) and never raises: no configured API key, no search
    results, a rate-limited response, or a network error all just leave that
    slide's picture(s) exactly as they were — image search is a quality
    enhancement, not a pipeline-critical step.
    """
    if not client.configured:
        return deck

    result = deck.model_copy(deep=True)
    for slide, content in zip(result.slides, deck_content.slides, strict=True):
        if not content.image_brief:
            continue
        pictures = [shape for shape in slide.shapes if isinstance(shape, Picture)]
        if not pictures:
            continue

        photo = client.find_photo(content.image_brief)
        if photo is None:
            continue

        encoded = base64.b64encode(photo.image_bytes).decode("ascii")
        attribution_text = f"Photo by {photo.photographer_name} on Unsplash"
        for shape in pictures:
            shape.image_bytes_b64 = encoded
            shape.content_type = photo.content_type
            # Crop fractions were framed for the template's *original*
            # image — meaningless (and potentially badly cropped) applied
            # to a differently-composed replacement photo.
            shape.crop_left = 0.0
            shape.crop_top = 0.0
            shape.crop_right = 0.0
            shape.crop_bottom = 0.0
            shape.attribution_text = attribution_text
            shape.attribution_url = photo.unsplash_url

    return result
