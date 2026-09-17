"""Tests for `inference.client.InferenceClient`, HTTP layer mocked via `httpx.MockTransport`.

    uv run pytest packages/inference
"""

from __future__ import annotations

import json

import httpx
import pytest
from inference import InferenceClient, InferenceError, InferenceSettings
from pydantic import BaseModel


class _Point(BaseModel):
    x: int
    y: int


def _client_with_handler(handler, api_key: str | None = "test-key") -> InferenceClient:
    settings = InferenceSettings(api_base="https://example.test/v1", api_key=api_key)
    http_client = httpx.Client(transport=httpx.MockTransport(handler), base_url=settings.api_base)
    return InferenceClient(settings=settings, http_client=http_client)


def test_complete_builds_correct_request_payload():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "hello"}}]}
        )

    client = _client_with_handler(handler)
    result = client.complete(
        model="qwen/qwen3-32b",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.4,
        max_tokens=100,
    )

    assert result == "hello"
    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer test-key"
    assert captured["body"] == {
        "model": "qwen/qwen3-32b",
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.4,
        "max_tokens": 100,
    }


def test_complete_structured_parses_valid_json_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps({"x": 1, "y": 2})}}]},
        )

    client = _client_with_handler(handler)
    result = client.complete_structured(
        model="qwen/qwen3-32b",
        system_prompt="sys",
        user_content="user",
        temperature=0.0,
        max_tokens=50,
        response_model=_Point,
    )

    assert result == _Point(x=1, y=2)


def test_complete_structured_sends_json_object_response_format():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps({"x": 1, "y": 2})}}]},
        )

    client = _client_with_handler(handler)
    client.complete_structured(
        model="qwen/qwen3-32b",
        system_prompt="sys",
        user_content="user",
        temperature=0.0,
        max_tokens=50,
        response_model=_Point,
    )

    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert captured["body"]["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "user"},
    ]


def test_complete_structured_raises_on_malformed_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "not json at all"}}]}
        )

    client = _client_with_handler(handler)
    with pytest.raises(InferenceError, match="malformed JSON"):
        client.complete_structured(
            model="qwen/qwen3-32b",
            system_prompt="sys",
            user_content="user",
            temperature=0.0,
            max_tokens=50,
            response_model=_Point,
        )


def test_complete_structured_raises_on_schema_mismatch():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps({"x": "not an int"})}}]},
        )

    client = _client_with_handler(handler)
    with pytest.raises(InferenceError):
        client.complete_structured(
            model="qwen/qwen3-32b",
            system_prompt="sys",
            user_content="user",
            temperature=0.0,
            max_tokens=50,
            response_model=_Point,
        )


def test_missing_api_key_raises_clear_runtime_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not send a request without an API key")

    client = _client_with_handler(handler, api_key=None)

    with pytest.raises(RuntimeError, match="INFERENCE_API_KEY"):
        client.complete(
            model="qwen/qwen3-32b",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.0,
            max_tokens=10,
        )
