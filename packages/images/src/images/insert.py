"""Composed deck -> real, on-topic photos in every photo slot of the template.

No LLM call here — the search query (`SlideContent.image_query`, short
English keywords; `image_brief` as a fallback) was already written by
`skills/slide-content`; this only turns it into real photos via image search
(`client.UnsplashClient` with a key, else the keyless `open_client`) and puts
them into the slide's photo slots.

A photo slot is a template picture that is a photo (not an icon or
illustration — see `neutral.is_template_photo`), including photos filled into
shapes (a portrait in a circle), and an empty picture placeholder. Each slot
on a slide gets its own photo — a team slide's four portraits are four
pictures, not one repeated. Slots left without a photo are handled by
`neutral.neutralize_template_photos`, so no template photo survives.

Split in two so the network part runs once per generation, not once per
density variant: `find_slide_photos` searches, `apply_photos` is the pure
swap reused for all three variants.
"""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor

from generator.content import DeckContent, SlideContent
from ir_schema import Deck, Picture, Slide, TextBoxShape

from images.client import Photo
from images.neutral import cover_frame, fit_to_frame, is_template_photo

# Below this share of the slide a picture is a logo or icon, not a photo slot.
_MIN_SLOT_AREA_FRACTION = 0.01
# Slides searched at once; also caps photos per slide.
_PARALLEL = 4
_MAX_SLOTS = 6


def _is_empty_picture_frame(shape) -> bool:
    return (
        isinstance(shape, TextBoxShape)
        and "PICTURE" in (shape.placeholder_type or "")
        and not any(r.text.strip() for p in shape.paragraphs for r in p.runs)
    )


def photo_slots(slide: Slide, slide_area: int) -> list[Picture | TextBoxShape]:
    """The slide's photo slots, biggest first."""
    slots = [
        s
        for s in slide.shapes
        if s.width * s.height >= _MIN_SLOT_AREA_FRACTION * slide_area
        and (
            (
                isinstance(s, Picture)
                and not s.is_background  # the slide's backdrop is design, kept as is
                and not s.image_replaced
                and is_template_photo(s)
            )
            or _is_empty_picture_frame(s)
        )
    ]
    return sorted(slots, key=lambda s: s.width * s.height, reverse=True)[:_MAX_SLOTS]


def _orientation(slot) -> str:
    ratio = slot.width / slot.height if slot.height else 1.0
    if ratio > 1.2:
        return "landscape"
    if ratio < 0.83:
        return "portrait"
    return "squarish"


def _queries(content: SlideContent) -> list[str]:
    """The slide's search query, then progressively simpler fallbacks.

    A specific multi-word query ("farmer market fresh vegetables crate")
    often has no hits where its first couple of words ("farmer market")
    have plenty — better a slightly broader on-topic photo than none.
    """
    query = (content.image_query or content.image_brief or "").strip()
    if not query:
        return []
    words = query.split()
    candidates = [query, " ".join(words[:2]), words[0]]
    return list(dict.fromkeys(q for q in candidates if q))


def find_slide_photos(deck: Deck, deck_content: DeckContent, client) -> dict[int, list[Photo]]:
    """Photos for each slide's slots, keyed by slide position; never raises.

    Slides are searched in parallel; a few spare results per slide let a
    photo already used on an earlier slide be skipped, so no photo repeats
    across the deck.
    """
    if not client.configured:
        return {}
    slide_area = deck.slide_width * deck.slide_height
    jobs = {}
    for i, (slide, content) in enumerate(zip(deck.slides, deck_content.slides, strict=True)):
        slots = photo_slots(slide, slide_area)
        queries = _queries(content)
        if slots and queries:
            jobs[i] = (queries, len(slots), _orientation(slots[0]))

    def search(job) -> list[Photo]:
        """Photos for one slide: the full query first, broader ones to top up."""
        queries, count, orientation = job
        found: list[Photo] = []
        for query in queries:
            if len(found) >= count + 2:
                break
            seen = {p.photo_id for p in found}
            try:
                more = client.find_photos(
                    query, count + 2 - len(found), orientation=orientation, exclude_ids=seen
                )
            except Exception:
                more = []
            found += [p for p in more if p.photo_id not in seen]
        return found

    with ThreadPoolExecutor(max_workers=_PARALLEL) as pool:
        results = dict(zip(jobs, pool.map(search, jobs.values()), strict=True))

    used: set[str] = set()
    photos: dict[int, list[Photo]] = {}
    for i in sorted(results):
        fresh = [p for p in results[i] if not p.photo_id or p.photo_id not in used]
        chosen = fresh[: jobs[i][1]]
        used.update(p.photo_id for p in chosen if p.photo_id)
        if chosen:
            photos[i] = chosen
    return photos


def place_image(slide: Slide, slot, image: bytes, content_type: str) -> Picture:
    """Put `image` into `slot` (a template photo or an empty picture frame)
    without changing the slide's structure: same frame, same place, the image
    cropped to the frame's shape. Returns the resulting Picture."""
    picture = (
        slot
        if isinstance(slot, Picture)
        else Picture(**slot.model_dump(exclude={"kind", "paragraphs"}))
    )
    original = base64.b64decode(picture.image_bytes_b64) if picture.image_bytes_b64 else b""
    crop = (picture.crop_left, picture.crop_top, picture.crop_right, picture.crop_bottom)
    # A cut-out (portrait on transparency) gets the image in an oval over the
    # same spot; any other frame the image cropped to its aspect ratio.
    fitted = fit_to_frame(image, original, crop) if original else None
    try:
        data, content_type = fitted or cover_frame(image, picture.width, picture.height)
    except Exception:  # not a raster PIL reads: put it in as is
        data = image
    # Crop fractions were framed for the template's own image.
    picture.crop_left = picture.crop_top = picture.crop_right = picture.crop_bottom = 0.0
    picture.image_bytes_b64 = base64.b64encode(data).decode("ascii")
    picture.content_type = content_type
    picture.image_replaced = True
    if picture is not slot:
        slide.shapes = [picture if s is slot else s for s in slide.shapes]
    return picture


def apply_user_images(
    deck: Deck, deck_content: DeckContent, images: list[tuple[str, str]]
) -> tuple[Deck, list[tuple[str, str]]]:
    """The user's own images where the writer chose them (`SlideContent.user_image`).

    Each goes into its slide's biggest photo slot. Returns the new deck (never
    mutates `deck`) and the images no slide asked for, in their order.
    """
    chosen = {
        i: slide.user_image - 1
        for i, slide in enumerate(deck_content.slides)
        if slide.user_image and 1 <= slide.user_image <= len(images)
    }
    if not chosen:
        return deck, images
    result = deck.model_copy(deep=True)
    slide_area = result.slide_width * result.slide_height
    placed: set[int] = set()
    for i, k in chosen.items():
        if i >= len(result.slides) or k in placed:
            continue
        slots = photo_slots(result.slides[i], slide_area)
        if not slots:
            continue
        content_type, data_b64 = images[k]
        place_image(result.slides[i], slots[0], base64.b64decode(data_b64), content_type)
        placed.add(k)
    return result, [img for k, img in enumerate(images) if k not in placed]


def apply_photos(deck: Deck, photos: dict[int, list[Photo]]) -> Deck:
    """Put each slide's photos into its slots, one photo per slot. Never mutates `deck`."""
    if not photos:
        return deck
    result = deck.model_copy(deep=True)
    slide_area = result.slide_width * result.slide_height
    for i, found in photos.items():
        slide = result.slides[i]
        for slot, photo in zip(photo_slots(slide, slide_area), found, strict=False):
            picture = place_image(slide, slot, photo.image_bytes, photo.content_type)
            if photo.photographer_name:  # Unsplash's terms; keyless sources carry none
                picture.attribution_text = f"Photo by {photo.photographer_name} on Unsplash"
                picture.attribution_url = photo.unsplash_url
    return result


def replace_pictures_with_photos(deck: Deck, deck_content: DeckContent, client) -> Deck:
    """`find_slide_photos` + `apply_photos` for a single deck; never raises."""
    return apply_photos(deck, find_slide_photos(deck, deck_content, client))
