"""Tests for `images.insert.replace_pictures_with_photos`.

uv run pytest packages/images
"""

from __future__ import annotations

import base64

import httpx
from generator.content import DeckContent, SlideContent
from images import Photo, UnsplashClient, UnsplashSettings, replace_pictures_with_photos
from ir_schema import Deck, Picture, Slide, TextBoxShape


def _picture(shape_id: int, image_bytes_b64: str | None = "original") -> Picture:
    return Picture(
        shape_id=shape_id,
        name=f"pic-{shape_id}",
        z_order=0,
        left=0,
        top=0,
        width=1_000_000,
        height=1_000_000,
        image_bytes_b64=image_bytes_b64,
        content_type="image/png",
        crop_left=0.1,
        crop_top=0.1,
        crop_right=0.1,
        crop_bottom=0.1,
    )


def _title(shape_id: int) -> TextBoxShape:
    return TextBoxShape(
        shape_id=shape_id, name=f"t-{shape_id}", z_order=1, left=0, top=0, width=1, height=1
    )


def _deck(slides: list[Slide]) -> Deck:
    return Deck(slide_width=9_144_000, slide_height=6_858_000, slides=slides)


def _client_returning(photo: Photo | None) -> UnsplashClient:
    settings = UnsplashSettings(access_key="test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(
            "client.find_photo should be monkeypatched by the fixture, not hit HTTP"
        )

    client = UnsplashClient(
        settings=settings, http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    client.find_photo = lambda query, orientation=None: photo  # type: ignore[method-assign]
    return client


_A_PHOTO = Photo(
    image_bytes=b"real-photo-bytes",
    content_type="image/jpeg",
    width=4000,
    height=3000,
    photographer_name="Jane Doe",
    photographer_url="https://unsplash.test/@jane",
    unsplash_url="https://unsplash.test/photos/abc123",
)


def test_slide_with_brief_gets_photo_and_attribution():
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_title(1), _picture(2)])])
    content = DeckContent(slides=[SlideContent(role="L", title="T", image_brief="a BMW on a road")])

    result = replace_pictures_with_photos(deck, content, _client_returning(_A_PHOTO))

    pic = next(s for s in result.slides[0].shapes if isinstance(s, Picture))
    assert pic.image_bytes_b64 == base64.b64encode(b"real-photo-bytes").decode("ascii")
    assert pic.content_type == "image/jpeg"
    assert pic.attribution_text == "Photo by Jane Doe on Unsplash"
    assert pic.attribution_url == "https://unsplash.test/photos/abc123"
    # Crop framed for the old image must not carry over to the new one.
    assert (pic.crop_left, pic.crop_top, pic.crop_right, pic.crop_bottom) == (0.0, 0.0, 0.0, 0.0)


def test_slide_without_brief_is_untouched():
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_title(1), _picture(2)])])
    content = DeckContent(slides=[SlideContent(role="L", title="T", image_brief=None)])

    result = replace_pictures_with_photos(deck, content, _client_returning(_A_PHOTO))

    pic = next(s for s in result.slides[0].shapes if isinstance(s, Picture))
    assert pic.image_bytes_b64 == "original"
    assert pic.attribution_text is None


def test_no_search_results_leaves_original_image():
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_picture(2)])])
    content = DeckContent(
        slides=[SlideContent(role="L", title="T", image_brief="something obscure")]
    )

    result = replace_pictures_with_photos(deck, content, _client_returning(None))

    pic = next(s for s in result.slides[0].shapes if isinstance(s, Picture))
    assert pic.image_bytes_b64 == "original"


def test_unconfigured_client_is_a_no_op():
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_picture(2)])])
    content = DeckContent(slides=[SlideContent(role="L", title="T", image_brief="BMW")])
    client = UnsplashClient(settings=UnsplashSettings(access_key=None))

    result = replace_pictures_with_photos(deck, content, client)

    assert result is deck  # short-circuited before any copy/search


def test_multiple_pictures_on_one_slide_get_the_same_photo():
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_picture(2, "a"), _picture(3, "b")])])
    content = DeckContent(slides=[SlideContent(role="L", title="T", image_brief="BMW")])

    result = replace_pictures_with_photos(deck, content, _client_returning(_A_PHOTO))

    pics = [s for s in result.slides[0].shapes if isinstance(s, Picture)]
    assert all(
        p.image_bytes_b64 == base64.b64encode(b"real-photo-bytes").decode("ascii") for p in pics
    )


def test_original_deck_is_never_mutated():
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_picture(2)])])
    content = DeckContent(slides=[SlideContent(role="L", title="T", image_brief="BMW")])

    replace_pictures_with_photos(deck, content, _client_returning(_A_PHOTO))

    pic = next(s for s in deck.slides[0].shapes if isinstance(s, Picture))
    assert pic.image_bytes_b64 == "original"
