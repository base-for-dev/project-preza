"""Tests for `images.client.UnsplashClient`, HTTP layer mocked via `httpx.MockTransport`.

    uv run pytest packages/images
"""

from __future__ import annotations

import httpx
from images import UnsplashClient, UnsplashSettings

_SEARCH_RESULT = {
    "results": [
        {
            "id": "abc123",
            "width": 4000,
            "height": 3000,
            "urls": {"regular": "https://images.unsplash.test/abc123.jpg"},
            "links": {
                "html": "https://unsplash.test/photos/abc123",
                "download_location": "https://api.unsplash.test/photos/abc123/download",
            },
            "user": {
                "name": "Jane Photographer",
                "links": {"html": "https://unsplash.test/@jane"},
            },
        }
    ]
}

_FAKE_JPEG_BYTES = b"\xff\xd8\xff\xe0fakejpegbytes"


def _client_with_handler(handler, access_key: str | None = "test-access-key") -> UnsplashClient:
    settings = UnsplashSettings(api_base="https://api.unsplash.test", access_key=access_key)
    http_client = httpx.Client(transport=httpx.MockTransport(handler), base_url=settings.api_base)
    return UnsplashClient(settings=settings, http_client=http_client)


def test_find_photo_returns_real_bytes_and_attribution():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "search/photos" in str(request.url):
            assert request.headers["authorization"] == "Client-ID test-access-key"
            assert "query=BMW" in str(request.url)
            return httpx.Response(200, json=_SEARCH_RESULT)
        if "abc123.jpg" in str(request.url):
            return httpx.Response(
                200, content=_FAKE_JPEG_BYTES, headers={"content-type": "image/jpeg"}
            )
        if "download" in str(request.url):
            return httpx.Response(200, json={"url": "https://images.unsplash.test/abc123.jpg"})
        raise AssertionError(f"unexpected request: {request.url}")

    client = _client_with_handler(handler)
    photo = client.find_photo("BMW")

    assert photo is not None
    assert photo.image_bytes == _FAKE_JPEG_BYTES
    assert photo.content_type == "image/jpeg"
    assert photo.photographer_name == "Jane Photographer"
    assert photo.photographer_url == "https://unsplash.test/@jane"
    assert photo.unsplash_url == "https://unsplash.test/photos/abc123"
    # Download tracking ping fired per Unsplash's API terms.
    assert any("download" in c for c in calls)


def test_find_photo_returns_none_without_access_key():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not make a request without an access key")

    client = _client_with_handler(handler, access_key=None)
    assert client.find_photo("BMW") is None


def test_find_photo_returns_none_on_no_results():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    client = _client_with_handler(handler)
    assert client.find_photo("something obscure") is None


def test_find_photo_returns_none_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"errors": ["Rate Limit Exceeded"]})

    client = _client_with_handler(handler)
    assert client.find_photo("BMW") is None


def test_find_photo_returns_none_on_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = _client_with_handler(handler)
    assert client.find_photo("BMW") is None


def test_configured_reflects_whether_access_key_is_set():
    settings_with_key = UnsplashSettings(access_key="k")
    settings_without_key = UnsplashSettings(access_key=None)
    assert UnsplashClient(settings=settings_with_key).configured is True
    assert UnsplashClient(settings=settings_without_key).configured is False
