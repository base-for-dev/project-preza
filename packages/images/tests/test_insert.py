"""Tests for `images.insert.replace_pictures_with_photos`.

uv run pytest packages/images
"""

from __future__ import annotations

import base64

import httpx
from generator.content import DeckContent, SlideContent
from images import (
    Photo,
    UnsplashClient,
    UnsplashSettings,
    apply_photos,
    find_slide_photos,
    replace_pictures_with_photos,
)
from ir_schema import Deck, Picture, Slide, TextBoxShape


def _picture(
    shape_id: int,
    image_bytes_b64: str | None = "original",
    width: int = 4_000_000,
    height: int = 3_000_000,
) -> Picture:
    return Picture(
        shape_id=shape_id,
        name=f"pic-{shape_id}",
        z_order=0,
        left=0,
        top=0,
        width=width,
        height=height,
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
    client.find_photo = lambda query, orientation=None, exclude_ids=None: photo  # type: ignore[method-assign]
    return client


_A_PHOTO = Photo(
    photo_id="abc123",
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


def _recording_client(photos_by_query: dict[str, list[Photo]]) -> tuple[UnsplashClient, list]:
    """Client whose find_photo answers from a table and records every call."""
    calls: list[tuple[str, str | None, set[str]]] = []
    client = UnsplashClient(settings=UnsplashSettings(access_key="test-key"))

    def find_photo(query, orientation=None, exclude_ids=None):
        excluded = set(exclude_ids or ())
        calls.append((query, orientation, excluded))
        return next(
            (p for p in photos_by_query.get(query, []) if p.photo_id not in excluded), None
        )

    client.find_photo = find_photo  # type: ignore[method-assign]
    return client, calls


def _photo(photo_id: str) -> Photo:
    return _A_PHOTO.model_copy(update={"photo_id": photo_id, "image_bytes": photo_id.encode()})


def test_image_query_is_preferred_over_brief():
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_picture(2)])])
    content = DeckContent(
        slides=[
            SlideContent(
                role="L", title="T", image_brief="Курьер с продуктами", image_query="courier groceries"
            )
        ]
    )
    client, calls = _recording_client({"courier groceries": [_A_PHOTO]})

    photos = find_slide_photos(deck, content, client)

    assert photos[0].photo_id == "abc123"
    assert calls[0][0] == "courier groceries"


def test_small_icons_and_logos_are_never_replaced():
    icon = _picture(3, "icon", width=300_000, height=300_000)
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_picture(2), icon])])
    content = DeckContent(slides=[SlideContent(role="L", title="T", image_query="farm")])

    result = replace_pictures_with_photos(deck, content, _client_returning(_A_PHOTO))

    pics = {s.shape_id: s for s in result.slides[0].shapes if isinstance(s, Picture)}
    assert pics[2].attribution_text is not None
    assert pics[3].image_bytes_b64 == "icon"


def test_slide_with_only_an_icon_makes_no_search():
    icon = _picture(3, "icon", width=300_000, height=300_000)
    deck = _deck([Slide(index=0, layout_name="L", shapes=[icon])])
    content = DeckContent(slides=[SlideContent(role="L", title="T", image_query="farm")])
    client, calls = _recording_client({"farm": [_A_PHOTO]})

    assert find_slide_photos(deck, content, client) == {}
    assert calls == []


def test_same_photo_is_not_reused_across_slides():
    deck = _deck([Slide(index=i, layout_name="L", shapes=[_picture(2)]) for i in range(2)])
    content = DeckContent(
        slides=[SlideContent(role="L", title="T", image_query="farm vegetables")] * 2
    )
    client, _ = _recording_client({"farm vegetables": [_photo("p1"), _photo("p2")]})

    photos = find_slide_photos(deck, content, client)

    assert [photos[0].photo_id, photos[1].photo_id] == ["p1", "p2"]


def test_falls_back_to_simpler_query_when_specific_one_finds_nothing():
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_picture(2)])])
    content = DeckContent(
        slides=[SlideContent(role="L", title="T", image_query="farmers market kazan crates")]
    )
    client, calls = _recording_client({"farmers market": [_A_PHOTO]})

    photos = find_slide_photos(deck, content, client)

    assert photos[0].photo_id == "abc123"
    assert [c[0] for c in calls] == ["farmers market kazan crates", "farmers market"]


def test_orientation_follows_picture_frame():
    wide = _deck([Slide(index=0, layout_name="L", shapes=[_picture(2, width=6_000_000, height=2_000_000)])])
    tall = _deck([Slide(index=0, layout_name="L", shapes=[_picture(2, width=2_000_000, height=5_000_000)])])
    content = DeckContent(slides=[SlideContent(role="L", title="T", image_query="farm")])

    client, calls = _recording_client({})
    find_slide_photos(wide, content, client)
    find_slide_photos(tall, content, client)

    assert calls[0][1] == "landscape"
    assert calls[-1][1] == "portrait"


def test_apply_photos_reuses_one_search_across_variants():
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_picture(2)])])
    photos = {0: _A_PHOTO}

    a, b = apply_photos(deck, photos), apply_photos(deck, photos)

    for d in (a, b):
        pic = next(s for s in d.slides[0].shapes if isinstance(s, Picture))
        assert pic.attribution_url == "https://unsplash.test/photos/abc123"
    assert apply_photos(deck, {}) is deck


def test_empty_picture_frames_get_images_demo_slides_first():
    from ir_schema import TextBoxShape

    from images import fill_empty_frames

    def frame(sid):
        return TextBoxShape(
            shape_id=sid, name="ph", z_order=0, left=0, top=0, width=3_000_000,
            height=2_000_000, is_placeholder=True, placeholder_type="PICTURE (18)",
        )

    deck = _deck(
        [
            Slide(index=0, layout_name="content-03", shapes=[frame(5)]),
            Slide(index=1, layout_name="demo-26", shapes=[frame(7)]),
        ]
    )

    result = fill_empty_frames(deck, [("image/png", "QQ==")])

    kinds = [[s.kind for s in slide.shapes] for slide in result.slides]
    assert kinds == [["text_box"], ["picture"]]  # the demo slide won the one image
    pic = result.slides[1].shapes[0]
    assert (pic.shape_id, pic.image_bytes_b64) == (7, "QQ==")
    assert deck.slides[1].shapes[0].kind == "text_box"  # input untouched
