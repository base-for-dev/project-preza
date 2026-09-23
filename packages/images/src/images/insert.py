"""Composed deck -> real, on-topic photos in place of template placeholder images.

No LLM call here — the search query (`SlideContent.image_query`, short
English keywords; `image_brief` as a fallback) was already written by
`skills/slide-content`; this only turns it into a real photo via Unsplash
search (see `client.py`) and swaps it into the deck's own `Picture` shapes.

Split in two so the network part runs once per generation, not once per
density variant: `find_slide_photos` searches (one query per slide), and
`apply_photos` is the pure swap, reused for all three variants — they share
the same slides and pictures, only their text differs. Kept as its own step, called after `layout.compose_deck`
rather than folded into it, so composition itself stays what its own
docstring promises: pure, deterministic, network-free Python.
"""

from __future__ import annotations

import base64

from generator.content import DeckContent, SlideContent
from ir_schema import Deck, Picture, Slide

from images.client import Photo, UnsplashClient

# Pictures smaller than this share of the slide are logos, icons, and
# decorative bits — the template's own design, not "a photo about the
# topic", so they're never replaced.
_MIN_PHOTO_AREA_FRACTION = 0.04


def _content_pictures(slide: Slide, slide_area: int) -> list[Picture]:
    return [
        shape
        for shape in slide.shapes
        if isinstance(shape, Picture)
        and shape.width * shape.height >= _MIN_PHOTO_AREA_FRACTION * slide_area
    ]


def _orientation(pictures: list[Picture]) -> str:
    """Unsplash orientation matching the slide's largest picture frame."""
    frame = max(pictures, key=lambda p: p.width * p.height)
    ratio = frame.width / frame.height if frame.height else 1.0
    if ratio > 1.2:
        return "landscape"
    if ratio < 0.83:
        return "portrait"
    return "squarish"


def _queries(content: SlideContent) -> list[str]:
    """The slide's search query, then progressively simpler fallbacks.

    A specific multi-word query ("farmer market fresh vegetables crate")
    often has zero Unsplash hits where its first couple of words
    ("farmer market") have plenty — better a slightly broader on-topic photo
    than the template's off-topic original.
    """
    query = (content.image_query or content.image_brief or "").strip()
    if not query:
        return []
    words = query.split()
    candidates = [query, " ".join(words[:2]), words[0]]
    return list(dict.fromkeys(q for q in candidates if q))


def find_slide_photos(
    deck: Deck, deck_content: DeckContent, client: UnsplashClient
) -> dict[int, Photo]:
    """One on-topic photo per slide that has a query and a photo-sized picture.

    Keyed by slide position. No photo is used twice in one deck: each search
    skips results already placed on an earlier slide. Never raises — a slide
    with no usable result is simply absent from the returned mapping.
    """
    if not client.configured:
        return {}

    slide_area = deck.slide_width * deck.slide_height
    used: set[str] = set()
    photos: dict[int, Photo] = {}
    for i, (slide, content) in enumerate(zip(deck.slides, deck_content.slides, strict=True)):
        pictures = _content_pictures(slide, slide_area)
        if not pictures:
            continue
        orientation = _orientation(pictures)
        for query in _queries(content):
            photo = client.find_photo(query, orientation=orientation, exclude_ids=used)
            if photo is not None:
                photos[i] = photo
                if photo.photo_id:
                    used.add(photo.photo_id)
                break
    return photos


def apply_photos(deck: Deck, photos: dict[int, Photo]) -> Deck:
    """Swap each found photo into its slide's photo-sized `Picture` shapes.

    All photo-sized pictures on a slide get the *same* photo — a slide's
    picture shapes are typically one image split across crop regions or a
    single hero image, and content generation writes one query per slide.
    Never mutates `deck` (returns a deep copy, matching `compose_deck`'s own
    no-mutation contract).
    """
    if not photos:
        return deck

    result = deck.model_copy(deep=True)
    slide_area = result.slide_width * result.slide_height
    for i, photo in photos.items():
        encoded = base64.b64encode(photo.image_bytes).decode("ascii")
        attribution_text = f"Photo by {photo.photographer_name} on Unsplash"
        for shape in _content_pictures(result.slides[i], slide_area):
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


def replace_pictures_with_photos(
    deck: Deck, deck_content: DeckContent, client: UnsplashClient
) -> Deck:
    """`find_slide_photos` + `apply_photos` for a single deck.

    Never raises: no configured API key, no search results, a rate-limited
    response, or a network error all just leave that slide's picture(s)
    exactly as they were — image search is a quality enhancement, not a
    pipeline-critical step.
    """
    if not client.configured:
        return deck
    return apply_photos(deck, find_slide_photos(deck, deck_content, client))
