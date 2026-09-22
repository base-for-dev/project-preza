"""Thin OpenAI-compatible chat client over httpx.

Sync only — this is a batch pipeline (generator/audit), not a UI. Provider is
whatever `INFERENCE_API_BASE` points at (OpenRouter today, a VK endpoint later —
see MODELS.md); nothing here is OpenRouter-specific beyond the default base URL.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from inference.settings import InferenceSettings

ModelT = TypeVar("ModelT", bound=BaseModel)


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
        # LLM completions routinely take 10-40s, and free-tier models seen
        # in practice up to ~160s on a single call (see MODELS.md) — httpx's
        # 5s default read timeout fires mid-generation and surfaces to
        # callers as a 500 that (since it bypasses CORSMiddleware's success
        # path) the browser reports as a CORS failure instead of the real
        # timeout. Budget: 4:30 (270s) per call.
        return httpx.Client(base_url=self._settings.api_base, timeout=270.0)

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
        try:
            response = client.post("/chat/completions", json=payload, headers=self._headers())
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
        # truncated content string — json.loads() on it fails downstream
        # with an opaque "malformed JSON" error that hides the real cause.
        # Surface it here instead, before that misleading error happens.
        if choice.get("finish_reason") == "length":
            raise InferenceError(
                f"provider truncated the response at max_tokens={max_tokens} "
                "(finish_reason: length) — raise max_tokens in the skill's config.yaml"
            )
        return content

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
