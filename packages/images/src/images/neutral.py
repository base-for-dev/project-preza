"""Template photos with no replacement -> a flat stand-in colour.

Templates ship with stock photos (a model on the cover, portraits on the team
slide, an office on the closing slide). Generation swaps them for photos found
for the talk (`insert`) or the user's own images (`frames`) — but when there
is no photo for a slide (no Unsplash key configured, no search hit, a frame
too small to search for), the template's picture used to stay: strangers'
faces in someone else's deck. Every photo still original after that is
replaced here with a plain fill in its own average colour, so the slide keeps
its design (the circle, the blob, the frame) without content that isn't the
user's. Icons, illustrations and 3D/gradient art are the template's design
and stay. A photo cut out on transparency (a team portrait) is still a photo:
told apart from smooth 3D art by its fine texture (hair, fabric), and
replaced by an oval over the same spot so the design keeps its layout.
"""

from __future__ import annotations

import base64
import io

from ir_schema import Deck, Picture

# Below this share of the slide a picture is an icon or logo, not a photo.
_MIN_AREA_FRACTION = 0.0005
# A photo has many colours; flat illustrations and icons few.
_MIN_PHOTO_COLOURS = 200
# Above this transparent share an image is a cut-out or decoration.
_MAX_TRANSPARENT_SHARE = 0.10
# A cut-out counts as a photo when this share of its inner pixels sits on a
# sharp edge — photos have texture, rendered 3D blobs and gradients don't
# (measured: portraits 0.035-0.2, 3D art <= 0.004).
_MIN_CUTOUT_TEXTURE = 0.02
_MIN_CUTOUT_PIXELS = 2000


def has_transparency(data: bytes) -> bool:
    from PIL import Image

    image = Image.open(io.BytesIO(data))
    if "A" not in image.getbands() and "transparency" not in image.info:
        return False
    alpha = image.convert("RGBA").resize((64, 64)).getchannel("A").tobytes()
    return sum(1 for v in alpha if v < 250) > _MAX_TRANSPARENT_SHARE * len(alpha)


def _cutout_texture(image) -> tuple[float, int]:
    """(share of inner opaque pixels on a sharp edge, how many were measured)."""
    from PIL import ImageFilter

    image = image.copy()
    image.thumbnail((256, 256))
    inner = image.getchannel("A").point(lambda v: 255 if v >= 250 else 0)
    inner = inner.filter(ImageFilter.MinFilter(7)).tobytes()  # drop the silhouette edge
    edges = image.convert("L").filter(ImageFilter.FIND_EDGES).tobytes()
    measured = [e for e, m in zip(edges, inner, strict=True) if m]
    if not measured:
        return 0.0, 0
    return sum(1 for e in measured if e > 40) / len(measured), len(measured)


def _is_photo(data: bytes) -> tuple[bool, tuple[int, int, int]]:
    """(looks like a photo, its average opaque colour)."""
    from PIL import Image

    image = Image.open(io.BytesIO(data))
    image.draft("RGB", (256, 256))  # fast path for JPEGs
    image = image.convert("RGBA")
    small = image.resize((64, 64))
    raw = small.tobytes()
    pixels = [tuple(raw[i : i + 4]) for i in range(0, len(raw), 4)]
    opaque = [p for p in pixels if p[3] >= 250]
    if not opaque:
        return False, (0, 0, 0)
    n = len(opaque)
    average = tuple(sum(p[i] for p in opaque) // n for i in range(3))
    if len(pixels) - n > _MAX_TRANSPARENT_SHARE * len(pixels):
        texture, measured = _cutout_texture(image)
        return texture >= _MIN_CUTOUT_TEXTURE and measured >= _MIN_CUTOUT_PIXELS, average  # type: ignore[return-value]
    colours = len({p[:3] for p in opaque})
    return colours >= _MIN_PHOTO_COLOURS, average  # type: ignore[return-value]


def _cutout_mask(original: bytes, limit: int, crop: tuple[float, float, float, float]):
    """An oval filling the cut-out's visible area — where a replacement goes.

    Not the silhouette itself: a new photo cut to the outline of the person
    it replaces reads as a strange shape (seen live: a brick wall in the
    form of a portrait); an avatar-style oval over the same spot reads right.
    """
    from PIL import Image, ImageDraw

    alpha = Image.open(io.BytesIO(original)).convert("RGBA").getchannel("A")
    # Only the part the frame shows (its crop) — the replacement goes in uncropped.
    left, top, right, bottom = crop
    w, h = alpha.size
    alpha = alpha.crop(
        (round(left * w), round(top * h), round(w * (1 - right)), round(h * (1 - bottom)))
    )
    alpha.thumbnail((limit, limit))
    mask = Image.new("L", alpha.size, 0)
    box = alpha.point(lambda v: 255 if v >= 128 else 0).getbbox()
    if box:
        ImageDraw.Draw(mask).ellipse(box, fill=255)
    return mask


def fit_to_frame(
    photo: bytes, original: bytes, crop: tuple[float, float, float, float] = (0, 0, 0, 0)
) -> tuple[bytes, str] | None:
    """`photo` in an oval over `original`'s visible spot when that is a transparent cut-out.

    Made for the frame uncropped (`crop` is the frame's current crop of
    `original`). None when `original` has no transparency (the photo goes in
    as is).
    """
    from PIL import Image, ImageOps

    if not has_transparency(original):
        return None
    mask = _cutout_mask(original, 1200, crop)
    # Faces and subjects sit high in most photos: crop a little above centre.
    fitted = ImageOps.fit(
        Image.open(io.BytesIO(photo)).convert("RGB"), mask.size, centering=(0.5, 0.35)
    )
    fitted.putalpha(mask)
    out = io.BytesIO()
    fitted.save(out, format="PNG", optimize=True)
    return out.getvalue(), "image/png"


def cover_frame(photo: bytes, width: int, height: int) -> tuple[bytes, str]:
    """`photo` cropped to the frame's aspect ratio (like CSS `cover`), so it
    fills the frame without being stretched. PNG keeps transparency; anything
    else becomes JPEG."""
    from PIL import Image, ImageOps

    image = Image.open(io.BytesIO(photo))
    ratio = width / height if height else 1.0
    w, h = image.size
    target = (w, round(w / ratio)) if w / h < ratio else (round(h * ratio), h)
    keep_alpha = "A" in image.getbands()
    image = image.convert("RGBA" if keep_alpha else "RGB")
    fitted = ImageOps.fit(image, target, centering=(0.5, 0.4))
    fitted.thumbnail((1600, 1600))
    out = io.BytesIO()
    if keep_alpha:
        fitted.save(out, format="PNG", optimize=True)
        return out.getvalue(), "image/png"
    fitted.save(out, format="JPEG", quality=88)
    return out.getvalue(), "image/jpeg"


def is_template_photo(picture: Picture) -> bool:
    """Whether `picture` holds a photo (not an icon, illustration or cut-out)."""
    if not picture.image_bytes_b64:
        return False
    try:
        return _is_photo(base64.b64decode(picture.image_bytes_b64))[0]
    except Exception:
        return False


def _flat_png(
    colour: tuple[int, int, int], original: bytes, crop: tuple[float, float, float, float]
) -> bytes:
    """A plain fill in `colour` — an oval over the spot if `original` is a cut-out."""
    from PIL import Image

    out = io.BytesIO()
    if has_transparency(original):
        mask = _cutout_mask(original, 600, crop)
        flat = Image.new("RGB", mask.size, colour)
        flat.putalpha(mask)
        flat.save(out, format="PNG", optimize=True)
    else:
        Image.new("RGB", (16, 16), colour).save(out, format="PNG")
    return out.getvalue()


def neutralize_template_photos(deck: Deck) -> Deck:
    """Replace every photo generation didn't swap with a flat colour. Never mutates `deck`."""
    result = deck.model_copy(deep=True)
    slide_area = result.slide_width * result.slide_height
    verdicts: dict[str, tuple[bool, tuple[int, int, int]]] = {}
    for slide in result.slides:
        for shape in slide.shapes:
            if not isinstance(shape, Picture) or shape.image_replaced or not shape.image_bytes_b64:
                continue
            if shape.is_background:  # the slide's backdrop is design, kept as is
                continue
            if shape.width * shape.height < _MIN_AREA_FRACTION * slide_area:
                continue
            key = shape.image_bytes_b64
            original = base64.b64decode(key)
            if key not in verdicts:
                try:
                    verdicts[key] = _is_photo(original)
                except Exception:  # unreadable or vector image: leave it be
                    verdicts[key] = (False, (0, 0, 0))
            photo, colour = verdicts[key]
            if not photo:
                continue
            crop = (shape.crop_left, shape.crop_top, shape.crop_right, shape.crop_bottom)
            shape.image_bytes_b64 = base64.b64encode(_flat_png(colour, original, crop)).decode(
                "ascii"
            )
            shape.content_type = "image/png"
            shape.crop_left = shape.crop_top = shape.crop_right = shape.crop_bottom = 0.0
            shape.image_replaced = True
    return result
