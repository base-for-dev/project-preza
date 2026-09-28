"""Tests for `images.insert` — photo slots and their replacement.

uv run pytest packages/images
"""

from __future__ import annotations

import base64
import io
import random

from generator.content import DeckContent, SlideContent
from images import (
    Photo,
    UnsplashClient,
    UnsplashSettings,
    apply_photos,
    find_slide_photos,
    neutralize_template_photos,
    replace_pictures_with_photos,
)
from ir_schema import Deck, Picture, Slide, TextBoxShape
from PIL import Image


def _png(noisy: bool) -> str:
    """A photo-like (many colours) or icon-like (one colour) image, base64."""
    rng = random.Random(0)
    image = Image.new("RGB", (64, 64), (200, 30, 30))
    if noisy:
        image.putdata([tuple(rng.randrange(256) for _ in range(3)) for _ in range(64 * 64)])
    out = io.BytesIO()
    image.save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode("ascii")


PHOTO = _png(noisy=True)
ICON = _png(noisy=False)


def _picture(
    shape_id: int, image: str = PHOTO, width: int = 4_000_000, height: int = 3_000_000
) -> Picture:
    return Picture(
        shape_id=shape_id,
        name=f"pic-{shape_id}",
        z_order=0,
        left=0,
        top=0,
        width=width,
        height=height,
        image_bytes_b64=image,
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


def _photo(photo_id: str, photographer: str = "") -> Photo:
    return Photo(
        photo_id=photo_id,
        image_bytes=photo_id.encode(),
        content_type="image/jpeg",
        width=4000,
        height=3000,
        photographer_name=photographer,
        unsplash_url="https://unsplash.test/photos/" + photo_id if photographer else "",
    )


class _FakeClient:
    """Answers find_photos from a table and records every call."""

    configured = True

    def __init__(self, table: dict[str, list[Photo]]) -> None:
        self.table = table
        self.calls: list[tuple[str, int, str | None]] = []

    def find_photos(self, query, count=1, *, orientation=None, exclude_ids=None):
        self.calls.append((query, count, orientation))
        return self.table.get(query, [])[:count]


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def test_photo_slot_gets_a_photo_without_attribution_from_keyless_search():
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_title(1), _picture(2)])])
    content = DeckContent(slides=[SlideContent(role="L", title="T", image_query="road car")])

    result = replace_pictures_with_photos(deck, content, _FakeClient({"road car": [_photo("p1")]}))

    pic = next(s for s in result.slides[0].shapes if isinstance(s, Picture))
    assert pic.image_bytes_b64 == _b64(b"p1") and pic.image_replaced
    assert pic.attribution_text is None
    # Crop framed for the old image must not carry over to the new one.
    assert (pic.crop_left, pic.crop_top, pic.crop_right, pic.crop_bottom) == (0.0, 0.0, 0.0, 0.0)


def test_unsplash_photo_keeps_its_attribution():
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_picture(2)])])
    photos = {0: [_photo("abc", photographer="Jane Doe")]}
    pic = next(s for s in apply_photos(deck, photos).slides[0].shapes if isinstance(s, Picture))
    assert pic.attribution_text == "Photo by Jane Doe on Unsplash"


def test_each_slot_on_a_slide_gets_its_own_photo():
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_picture(2), _picture(3)])])
    content = DeckContent(slides=[SlideContent(role="L", title="T", image_query="team")])
    client = _FakeClient({"team": [_photo("a"), _photo("b"), _photo("c")]})

    result = replace_pictures_with_photos(deck, content, client)

    images = {s.image_bytes_b64 for s in result.slides[0].shapes if isinstance(s, Picture)}
    assert images == {_b64(b"a"), _b64(b"b")}


def test_icons_and_small_pictures_are_not_photo_slots():
    small = _picture(3, width=200_000, height=200_000)
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_picture(2, ICON), small])])
    content = DeckContent(slides=[SlideContent(role="L", title="T", image_query="farm")])
    client = _FakeClient({"farm": [_photo("x")]})

    assert find_slide_photos(deck, content, client) == {}
    assert client.calls == []


def test_empty_picture_placeholder_is_a_photo_slot():
    frame = TextBoxShape(
        shape_id=5,
        name="ph",
        z_order=0,
        left=0,
        top=0,
        width=3_000_000,
        height=2_000_000,
        is_placeholder=True,
        placeholder_type="PICTURE (18)",
    )
    deck = _deck([Slide(index=0, layout_name="L", shapes=[frame])])
    content = DeckContent(slides=[SlideContent(role="L", title="T", image_query="city")])

    result = replace_pictures_with_photos(deck, content, _FakeClient({"city": [_photo("c1")]}))

    pic = result.slides[0].shapes[0]
    assert isinstance(pic, Picture) and pic.image_bytes_b64 == _b64(b"c1")


def test_slide_without_query_is_untouched():
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_picture(2)])])
    content = DeckContent(slides=[SlideContent(role="L", title="T")])
    result = replace_pictures_with_photos(deck, content, _FakeClient({}))
    assert result.slides[0].shapes[0].image_bytes_b64 == PHOTO


def test_unconfigured_client_is_a_no_op():
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_picture(2)])])
    content = DeckContent(slides=[SlideContent(role="L", title="T", image_brief="BMW")])
    client = UnsplashClient(settings=UnsplashSettings(access_key=None))
    assert replace_pictures_with_photos(deck, content, client) is deck


def test_original_deck_is_never_mutated():
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_picture(2)])])
    content = DeckContent(slides=[SlideContent(role="L", title="T", image_query="q")])
    replace_pictures_with_photos(deck, content, _FakeClient({"q": [_photo("n")]}))
    assert deck.slides[0].shapes[0].image_bytes_b64 == PHOTO


def test_image_query_is_preferred_over_brief():
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_picture(2)])])
    content = DeckContent(
        slides=[
            SlideContent(role="L", title="T", image_brief="Курьер", image_query="courier groceries")
        ]
    )
    client = _FakeClient({"courier groceries": [_photo("abc")]})
    assert find_slide_photos(deck, content, client)[0][0].photo_id == "abc"
    assert client.calls[0][0] == "courier groceries"


def test_same_photo_is_not_reused_across_slides():
    deck = _deck([Slide(index=i, layout_name="L", shapes=[_picture(2)]) for i in range(2)])
    content = DeckContent(slides=[SlideContent(role="L", title="T", image_query="farm")] * 2)
    client = _FakeClient({"farm": [_photo("p1"), _photo("p2"), _photo("p3")]})

    photos = find_slide_photos(deck, content, client)

    assert [photos[0][0].photo_id, photos[1][0].photo_id] == ["p1", "p2"]


def test_falls_back_to_simpler_query_when_specific_one_finds_nothing():
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_picture(2)])])
    content = DeckContent(
        slides=[SlideContent(role="L", title="T", image_query="farmers market kazan crates")]
    )
    client = _FakeClient({"farmers market": [_photo("abc")]})

    photos = find_slide_photos(deck, content, client)

    assert photos[0][0].photo_id == "abc"
    assert [c[0] for c in client.calls][:2] == ["farmers market kazan crates", "farmers market"]


def test_orientation_follows_picture_frame():
    wide = _deck(
        [Slide(index=0, layout_name="L", shapes=[_picture(2, width=6_000_000, height=2_000_000)])]
    )
    tall = _deck(
        [Slide(index=0, layout_name="L", shapes=[_picture(2, width=2_000_000, height=5_000_000)])]
    )
    content = DeckContent(slides=[SlideContent(role="L", title="T", image_query="farm")])
    client = _FakeClient({})
    find_slide_photos(wide, content, client)
    find_slide_photos(tall, content, client)
    assert client.calls[0][2] == "landscape"
    assert client.calls[-1][2] == "portrait"


def test_leftover_template_photo_becomes_flat_colour_icons_stay():
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_picture(2), _picture(3, ICON)])])
    result = neutralize_template_photos(deck)
    photo, icon = result.slides[0].shapes
    assert photo.image_replaced and photo.image_bytes_b64 != PHOTO
    assert not icon.image_replaced and icon.image_bytes_b64 == ICON


def test_empty_picture_frames_get_images_demo_slides_first():
    from images import fill_empty_frames
    from ir_schema import TextBoxShape

    def frame(sid):
        return TextBoxShape(
            shape_id=sid,
            name="ph",
            z_order=0,
            left=0,
            top=0,
            width=3_000_000,
            height=2_000_000,
            is_placeholder=True,
            placeholder_type="PICTURE (18)",
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


def _cutout(textured: bool) -> str:
    """A circle cut-out on transparency: noisy (a photo) or smooth (3D art)."""
    from PIL import ImageDraw

    rng = random.Random(1)
    image = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    fill = Image.new("RGBA", (200, 200))
    if textured:
        fill.putdata([(*(rng.randrange(256) for _ in range(3)), 255) for _ in range(200 * 200)])
    else:
        fill.putdata([(x, 100, 200 - x, 255) for _ in range(200) for x in range(200)])
    mask = Image.new("L", (200, 200), 0)
    ImageDraw.Draw(mask).ellipse((10, 10, 190, 190), fill=255)
    image.paste(fill, (0, 0), mask)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode("ascii")


def test_cut_out_portrait_is_a_photo_but_smooth_3d_art_is_not():
    deck = _deck(
        [
            Slide(
                index=0,
                layout_name="L",
                shapes=[_picture(2, _cutout(textured=True)), _picture(3, _cutout(textured=False))],
            )
        ]
    )
    portrait, art = neutralize_template_photos(deck).slides[0].shapes
    assert portrait.image_replaced and not art.image_replaced
    # The stand-in is an oval over the spot: transparent around it.
    flat = Image.open(io.BytesIO(base64.b64decode(portrait.image_bytes_b64)))
    assert flat.mode == "RGBA" and flat.getpixel((0, 0))[3] == 0


def test_new_photo_takes_a_cut_outs_silhouette():
    real_photo = io.BytesIO()
    Image.new("RGB", (300, 200), (20, 200, 90)).save(real_photo, format="JPEG")
    deck = _deck([Slide(index=0, layout_name="L", shapes=[_picture(2, _cutout(textured=True))])])
    photo = _photo("x").model_copy(update={"image_bytes": real_photo.getvalue()})
    pic = apply_photos(deck, {0: [photo]}).slides[0].shapes[0]
    placed = Image.open(io.BytesIO(base64.b64decode(pic.image_bytes_b64)))
    assert pic.content_type == "image/png" and placed.getpixel((0, 0))[3] == 0
    assert pic.crop_left == 0.0  # made for the frame's visible part, uncropped


def test_background_picture_is_never_a_photo_slot_nor_neutralized():
    backdrop = _picture(2, width=9_144_000, height=6_858_000).model_copy(
        update={"is_background": True}
    )
    deck = _deck([Slide(index=0, layout_name="L", shapes=[backdrop])])
    content = DeckContent(slides=[SlideContent(role="L", title="T", image_query="farm")])
    client = _FakeClient({"farm": [_photo("x")]})

    assert find_slide_photos(deck, content, client) == {}
    assert neutralize_template_photos(deck).slides[0].shapes[0].image_bytes_b64 == PHOTO


def test_user_image_goes_where_the_writer_put_it_cropped_to_the_frame():
    from images import apply_user_images

    wide = io.BytesIO()
    Image.new("RGB", (400, 100), (10, 20, 30)).save(wide, format="PNG")
    user = [("image/png", base64.b64encode(wide.getvalue()).decode()), ("image/png", PHOTO)]
    deck = _deck(
        [
            Slide(index=0, layout_name="L", shapes=[_picture(2)]),
            Slide(
                index=1, layout_name="L", shapes=[_picture(3, width=3_000_000, height=3_000_000)]
            ),
        ]
    )
    content = DeckContent(
        slides=[
            SlideContent(role="L", title="A"),
            SlideContent(role="L", title="B", user_image=1),
        ]
    )

    result, unused = apply_user_images(deck, content, user)

    assert result.slides[0].shapes[0].image_bytes_b64 == PHOTO  # untouched
    pic = result.slides[1].shapes[0]
    placed = Image.open(io.BytesIO(base64.b64decode(pic.image_bytes_b64)))
    assert pic.image_replaced and placed.size[0] == placed.size[1]  # square frame, not stretched
    assert unused == [user[1]]
