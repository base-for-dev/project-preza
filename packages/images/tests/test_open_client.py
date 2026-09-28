"""Keyless image search (images.open_client), with a mocked network.

uv run pytest packages/images
"""

import io

import httpx
from images import OpenImageClient
from PIL import Image


def _jpeg(width: int = 800) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, 600), (90, 140, 60)).save(out, format="JPEG")
    return out.getvalue()


def _client(openverse_status: int = 200) -> OpenImageClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.openverse.org":
            if openverse_status != 200:
                return httpx.Response(openverse_status)
            results = [
                {"id": f"ov{i}", "url": f"https://img.test/ov{i}.jpg", "width": 800}
                for i in range(3)
            ]
            return httpx.Response(200, json={"results": results})
        if request.url.host == "commons.wikimedia.org":
            pages = {
                "1": {
                    "pageid": 1,
                    "index": 1,
                    "imageinfo": [
                        {"mime": "image/jpeg", "width": 1600, "thumburl": "https://img.test/c1.jpg"}
                    ],
                }
            }
            return httpx.Response(200, json={"query": {"pages": pages}})
        return httpx.Response(200, content=_jpeg(), headers={"content-type": "image/jpeg"})

    return OpenImageClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_returns_distinct_real_images_skipping_excluded():
    photos = _client().find_photos("farm", 2, exclude_ids={"ov0"})
    assert [p.photo_id for p in photos] == ["ov1", "ov2"]
    assert all(p.image_bytes.startswith(b"\xff\xd8") and not p.photographer_name for p in photos)


def test_throttled_openverse_falls_back_to_wikimedia_commons():
    photos = _client(openverse_status=429).find_photos("farm", 1)
    assert [p.photo_id for p in photos] == ["commons:1"]
