"""Keyless image search -> real photos for a slide's `image_query`.

For personal use without an Unsplash key: Openverse (openly licensed images
from Flickr, Wikimedia and others; no key needed) and, when it's throttled
or finds nothing, Wikimedia Commons. Same contract as `UnsplashClient`:
`find_photos` returns real image bytes or an empty list — never raises, since
a missing photo is never fatal to generation.

No attribution is attached: the project is for personal use (see the user's
decision); the `Photo` attribution fields stay empty.
"""

from __future__ import annotations

import io

import httpx

from images.client import Photo

_OPENVERSE = "https://api.openverse.org/v1/images/"
_COMMONS = "https://commons.wikimedia.org/w/api.php"
_HEADERS = {"User-Agent": "preza/0.1 (personal slide generator)"}
_TIMEOUT = 15.0
_CANDIDATES = 20
# Smaller images look blurry on a 16:9 slide (and a thin panorama cropped
# into a round or square frame leaves a tiny image).
_MIN_WIDTH = 640
_MIN_HEIGHT = 400
_ASPECT = {"landscape": "wide", "portrait": "tall", "squarish": "square"}


def _decodable(data: bytes) -> tuple[int, int] | None:
    """(width, height) if `data` is a raster image PIL can open."""
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(data))
        image.verify()
        return image.size
    except Exception:
        return None


class OpenImageClient:
    """Openverse, then Wikimedia Commons. Always "configured": no key needed."""

    configured = True

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self._http_client = http_client

    def _client(self) -> httpx.Client:
        return self._http_client or httpx.Client(
            timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True
        )

    def _openverse(
        self, client: httpx.Client, query: str, orientation: str | None
    ) -> list[tuple[str, str]]:
        params: dict[str, str | int] = {"q": query, "page_size": _CANDIDATES, "mature": "false"}
        if orientation in _ASPECT:
            params["aspect_ratio"] = _ASPECT[orientation]
        resp = client.get(_OPENVERSE, params=params)
        resp.raise_for_status()
        return [
            (r["id"], r["url"])
            for r in resp.json().get("results", [])
            if r.get("url") and (r.get("width") or _MIN_WIDTH) >= _MIN_WIDTH
        ]

    def _commons(self, client: httpx.Client, query: str) -> list[tuple[str, str]]:
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"{query} filetype:bitmap",
            "gsrnamespace": 6,
            "gsrlimit": _CANDIDATES,
            "prop": "imageinfo",
            "iiprop": "url|size|mime",
            "iiurlwidth": 1280,
        }
        resp = client.get(_COMMONS, params=params)
        resp.raise_for_status()
        pages = sorted(
            resp.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0)
        )
        found = []
        for page in pages:
            info = (page.get("imageinfo") or [{}])[0]
            if (
                info.get("mime") in ("image/jpeg", "image/png")
                and info.get("width", 0) >= _MIN_WIDTH
            ):
                found.append(
                    (f"commons:{page.get('pageid')}", info.get("thumburl") or info.get("url"))
                )
        return found

    def find_photos(
        self,
        query: str,
        count: int = 1,
        *,
        orientation: str | None = None,
        exclude_ids: set[str] | None = None,
    ) -> list[Photo]:
        """Up to `count` different photos for `query`, skipping `exclude_ids`."""
        excluded = exclude_ids or set()
        client = self._client()
        photos: list[Photo] = []
        try:
            for source in ("openverse", "commons"):
                try:
                    candidates = (
                        self._openverse(client, query, orientation)
                        if source == "openverse"
                        else self._commons(client, query)
                    )
                except (httpx.HTTPError, ValueError, KeyError):
                    continue  # throttled / down: try the next source
                for photo_id, url in candidates:
                    if len(photos) >= count:
                        return photos
                    if photo_id in excluded or any(p.photo_id == photo_id for p in photos):
                        continue
                    try:
                        image = client.get(url)
                        image.raise_for_status()
                    except httpx.HTTPError:
                        continue
                    size = _decodable(image.content)
                    if size is None or size[0] < _MIN_WIDTH or size[1] < _MIN_HEIGHT:
                        continue
                    photos.append(
                        Photo(
                            photo_id=photo_id,
                            image_bytes=image.content,
                            content_type=image.headers.get("content-type", "image/jpeg").split(";")[
                                0
                            ],
                            width=size[0],
                            height=size[1],
                        )
                    )
                # Too few here: top up from the next source.
            return photos
        finally:
            if self._http_client is None:
                client.close()

    def find_photo(
        self, query: str, *, orientation: str | None = None, exclude_ids: set[str] | None = None
    ) -> Photo | None:
        found = self.find_photos(query, 1, orientation=orientation, exclude_ids=exclude_ids)
        return found[0] if found else None
