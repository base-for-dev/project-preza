"""Unsplash search -> a real photo's bytes, for one slide's `image_brief`.

Scope is deliberately narrow: one function, `find_photo(query)`, that returns
real JPEG bytes plus the attribution Unsplash's API terms require, or `None`
on anything short of success (no key configured, no results, rate-limited,
network error) — a missing photo is never fatal to the pipeline, the caller
just leaves the template's own picture in place (see `packages/layout`'s
`replace_pictures_with_photos`).

Unsplash's API Guidelines (https://help.unsplash.com/en/articles/2511245)
require two things beyond the search call itself, both handled here:
- A "download" tracking ping (GET the result's `download_location`) whenever
  a photo is actually used, not just previewed in search results.
- Attribution (photographer name + link back to Unsplash) wherever the photo
  is shown — `Photo.attribution` carries this back to the caller to render.
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel

from images.settings import UnsplashSettings


class Photo(BaseModel):
    image_bytes: bytes
    content_type: str
    width: int
    height: int
    # Required by Unsplash's API terms wherever the photo is displayed:
    # "Photo by {photographer_name} on Unsplash" linking both URLs.
    photographer_name: str
    photographer_url: str
    unsplash_url: str


class UnsplashClient:
    def __init__(
        self,
        settings: UnsplashSettings | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings or UnsplashSettings()
        self._http_client = http_client

    def _client(self) -> httpx.Client:
        if self._http_client is not None:
            return self._http_client
        return httpx.Client(
            base_url=self._settings.api_base, timeout=self._settings.request_timeout
        )

    @property
    def configured(self) -> bool:
        return bool(self._settings.access_key)

    def find_photo(self, query: str, *, orientation: str | None = None) -> Photo | None:
        """Search Unsplash for `query`, return the top result's real bytes.

        Returns `None` — never raises — on anything short of a usable photo:
        no API key configured, no search results, a rate-limited/error
        response, or a network failure. Image search is an enhancement, not
        a pipeline-critical step; the caller's fallback (keep the template's
        own picture) is always a safe, valid result.
        """
        if not self._settings.access_key:
            return None

        client = self._client()
        headers = {"Authorization": f"Client-ID {self._settings.access_key}"}
        params: dict[str, str | int] = {"query": query, "per_page": 1}
        if orientation:
            params["orientation"] = orientation

        try:
            search = client.get("/search/photos", params=params, headers=headers)
            search.raise_for_status()
            results = search.json().get("results", [])
            if not results:
                return None
            result = results[0]

            image_url = result["urls"]["regular"]
            image_resp = client.get(image_url)
            image_resp.raise_for_status()

            # API terms: ping this whenever the photo is actually used.
            download_location = result.get("links", {}).get("download_location")
            if download_location:
                client.get(download_location, headers=headers)

            content_type = image_resp.headers.get("content-type", "image/jpeg")
            return Photo(
                image_bytes=image_resp.content,
                content_type=content_type,
                width=result.get("width", 0),
                height=result.get("height", 0),
                photographer_name=result.get("user", {}).get("name", "Unsplash"),
                photographer_url=result.get("user", {})
                .get("links", {})
                .get("html", "https://unsplash.com"),
                unsplash_url=result.get("links", {}).get("html", "https://unsplash.com"),
            )
        except (httpx.HTTPError, KeyError, ValueError):
            # Network error, unexpected response shape, bad status — image
            # search failing is never worth taking down the whole generation.
            return None
        finally:
            if self._http_client is None:
                client.close()
