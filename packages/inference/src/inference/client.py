"""Thin OpenAI-compatible chat client over httpx.

Sync only — this is a batch pipeline (generator/audit), not a UI. Provider is
whatever `INFERENCE_API_BASE` points at (OpenRouter today, a VK endpoint later —
see MODELS.md); nothing here is OpenRouter-specific beyond the default base URL.
"""

from __future__ import annotations

import json
import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from inference.settings import InferenceSettings

ModelT = TypeVar("ModelT", bound=BaseModel)

# Transport-level failures worth one immediate retry: the connection dropped or
# the TLS stream ended mid-response (both observed intermittently against the
# OpenRouter free pool). A `ReadTimeout` is deliberately excluded — if the model
# genuinely needs longer than the read timeout, retrying just waits and fails
# again; that's a timeout-tuning problem, not a transient-blip problem.
_RETRYABLE = (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ConnectTimeout)


def text_content(text: str) -> dict[str, Any]:
    """A plain-text content part, OpenAI/OpenRouter chat format."""
    return {"type": "text", "text": text}


def image_content(url: str) -> dict[str, Any]:
    """An image content part. `url` may be a normal URL or a `data:` URI."""
    return {"type": "image_url", "image_url": {"url": url}}


class InferenceError(RuntimeError):
    """Raised when the provider returns something the caller can't use."""


class InferenceClient:
    def __init__(
        self,
        settings: InferenceSettings | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings or InferenceSettings()
        self._http_client = http_client

    def _client(self) -> httpx.Client:
        if self._http_client is not None:
            return self._http_client
        # LLM completions routinely take tens of seconds, and free-tier models
        # seen in practice up to ~160s on a single call (see MODELS.md) —
        # httpx's 5s default read timeout fires mid-generation and surfaces
        # to callers as a 500 that (since it bypasses CORSMiddleware's
        # success path) the browser reports as a CORS failure instead of the
        # real timeout. The read budget is generous and configurable (see
        # InferenceSettings.request_timeout, default 270s / 4:30); connect
        # stays short so a dead endpoint fails fast instead of hanging.
        timeout = httpx.Timeout(self._settings.request_timeout, connect=10.0)
        return httpx.Client(base_url=self._settings.api_base, timeout=timeout)

    def _headers(self) -> dict[str, str]:
        if not self._settings.api_key:
            raise RuntimeError(
                "INFERENCE_API_KEY is not set. Add your OpenRouter API key to .env "
                "(see .env.example) before making inference calls."
            )
        return {
            "Authorization": f"Bearer {self._settings.api_key}",
            "Content-Type": "application/json",
        }

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Send a chat completion request, return the assistant's raw text content."""
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        client = self._client()
        headers = self._headers()
        try:
            response = self._post_with_retry(client, payload, headers)
            response.raise_for_status()
        finally:
            if self._http_client is None:
                client.close()

        body = response.json()
        try:
            choice = body["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise InferenceError(f"unexpected response shape from provider: {body}") from exc

        # A response cut off by max_tokens comes back as valid HTTP with a
        # truncated (or null — see the reasoning-model case below) content
        # field — json.loads() on it fails downstream with an opaque
        # "malformed JSON"/TypeError that hides the real cause. Surface it
        # here instead, before that misleading error happens.
        if choice.get("finish_reason") == "length":
            raise InferenceError(
                f"provider truncated the response at max_tokens={max_tokens} "
                "(finish_reason: length) — raise max_tokens in the skill's config.yaml"
            )
        return content

    def _post_with_retry(
        self,
        client: httpx.Client,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> httpx.Response:
        """POST the completion, retrying once per transient transport blip.

        Only `_RETRYABLE` errors (dropped connection / SSL EOF) are retried,
        with a short linear backoff. Everything else — read timeouts, HTTP
        error statuses — propagates on the first occurrence.
        """
        attempts = self._settings.max_retries + 1
        for attempt in range(attempts):
            try:
                return client.post("/chat/completions", json=payload, headers=headers)
            except _RETRYABLE:
                if attempt == attempts - 1:
                    raise
                time.sleep(0.5 * (attempt + 1))
        # Unreachable: the loop either returns or raises on the last attempt.
        raise AssertionError("retry loop exited without returning")

    def complete_structured(
        self,
        *,
        model: str,
        system_prompt: str,
        user_content: str | list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        response_model: type[ModelT],
    ) -> ModelT:
        """Send a chat completion request and parse the reply as JSON matching `response_model`.

        Raises `InferenceError` if the provider's response isn't valid JSON, or is
        JSON that doesn't validate against `response_model`.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        raw = self.complete(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise InferenceError(
                f"provider returned malformed JSON for {response_model.__name__}: {raw!r}"
            ) from exc

        try:
            return response_model.model_validate(parsed)
        except ValidationError as exc:
            raise InferenceError(
                f"provider's JSON doesn't match {response_model.__name__}: {exc}"
            ) from exc
