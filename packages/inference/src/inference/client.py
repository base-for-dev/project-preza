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

# Passes over a skill's model chain before giving up, and the pause between.
_CHAIN_ROUNDS = 2
_CHAIN_PAUSE_SECONDS = 4.0


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
        timeout: float | None = None,
    ) -> str:
        """Send a chat completion request, return the assistant's raw text content."""
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            # Some models (e.g. qwen3.8-27b) are "thinking" models that spend
            # completion tokens on a hidden reasoning trace before the actual
            # answer. On a full-size prompt that reasoning alone can consume
            # the whole max_tokens budget, so the model hits finish_reason
            # "length" with an EMPTY content field — a 100% reproducible
            # failure, not flakiness (confirmed live: 4096/4096 tokens spent
            # on reasoning, content=None). Disabling reasoning is a no-op for
            # non-thinking models (confirmed live against qwen3-30b-a3b) and
            # a required off switch for thinking ones — this is a batch
            # structured-output pipeline, not a chat UI, so the trace is
            # never shown to a user anyway.
            "reasoning": {"enabled": False},
        }
        if response_format is not None:
            payload["response_format"] = response_format

        client = self._client()
        headers = self._headers()
        try:
            response = self._post_with_retry(client, payload, headers, timeout)
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

        # A response cut off by max_tokens comes back as valid HTTP with
        # either a truncated content string, or — for a "thinking" model
        # that spent its whole budget on a hidden reasoning trace before any
        # answer (confirmed live: 4096/4096 tokens on reasoning, content:
        # null) — a null content field. Either way, json.loads() on it fails
        # downstream with an opaque "malformed JSON"/TypeError that hides
        # the real cause. Surface it here instead, before that happens.
        if choice.get("finish_reason") == "length":
            raise InferenceError(
                f"provider truncated the response at max_tokens={max_tokens} "
                "(finish_reason: length) — raise max_tokens in the skill's "
                "config.yaml, or the model spent its budget on a hidden "
                "reasoning trace instead of the answer"
            )
        if content is None:
            # Belt-and-suspenders: some other provider-side empty completion
            # that isn't flagged via finish_reason "length" at all.
            raise InferenceError(
                f"provider returned no content for model {model!r} "
                f"(finish_reason={choice.get('finish_reason')!r})"
            )
        return content

    def _post_with_retry(
        self,
        client: httpx.Client,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: float | None = None,
    ) -> httpx.Response:
        """POST the completion, retrying once per transient transport blip.

        Only `_RETRYABLE` errors (dropped connection / SSL EOF) are retried,
        with a short linear backoff. Everything else — read timeouts, HTTP
        error statuses — propagates on the first occurrence.
        """
        attempts = self._settings.max_retries + 1
        for attempt in range(attempts):
            try:
                if timeout is None:
                    return client.post("/chat/completions", json=payload, headers=headers)
                return client.post(
                    "/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=httpx.Timeout(timeout, connect=10.0),
                )
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
        fallback_models: list[str] | tuple[str, ...] = (),
        timeout: float | None = None,
    ) -> ModelT:
        """Send a chat completion request and parse the reply as JSON matching `response_model`.

        On a rate limit (429), no credit (402), withdrawn model (404), provider error
        (5xx), timeout, or an unusable
        reply from `model`, the same request is retried on each of
        `fallback_models` in order; if the whole chain fails, it's tried once
        more after a short pause, then the last error propagates.
        Missing API key and other 4xx errors are never retried — every model
        would fail the same way.

        Raises `InferenceError` if the provider's response isn't valid JSON, or is
        JSON that doesn't validate against `response_model`.
        """
        models = [model, *fallback_models]
        # Free-pool 429/503s clear within seconds and don't count against the
        # daily free quota, so a whole chain failing earns one more pass after
        # a short pause. Models that failed permanently (402 no credit, 404
        # withdrawn) are not retried.
        permanent: set[str] = set()
        last_error: Exception | None = None
        rounds = _CHAIN_ROUNDS if fallback_models else 1
        for round_ in range(rounds):
            if round_:
                time.sleep(_CHAIN_PAUSE_SECONDS)
            for current in (m for m in models if m not in permanent):
                try:
                    return self._complete_structured_once(
                        current, system_prompt, user_content, temperature, max_tokens,
                        response_model, timeout,
                    )
                except (httpx.TimeoutException, httpx.TransportError, InferenceError) as exc:
                    last_error = exc
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    # 402: no credit for a paid model — a free fallback still
                    # works. 404: the provider withdrew the model (free models
                    # come and go without notice — both nex free models
                    # vanished overnight).
                    if status in (402, 404):
                        permanent.add(current)
                    elif not (status == 429 or status >= 500):
                        raise
                    last_error = exc
            if len(permanent) == len(models):
                break
        assert last_error is not None
        raise last_error

    def _complete_structured_once(
        self,
        model: str,
        system_prompt: str,
        user_content: str | list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        response_model: type[ModelT],
        timeout: float | None,
    ) -> ModelT:
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
            timeout=timeout,
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
