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
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})

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
        "reasoning": {"enabled": False},
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
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json at all"}}]})

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


def test_transient_transport_error_is_retried_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.RemoteProtocolError("server disconnected mid-response")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    settings = InferenceSettings(
        api_base="https://example.test/v1", api_key="test-key", max_retries=1
    )
    http_client = httpx.Client(transport=httpx.MockTransport(handler), base_url=settings.api_base)
    client = InferenceClient(settings=settings, http_client=http_client)

    result = client.complete(
        model="qwen/qwen3-32b",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.0,
        max_tokens=10,
    )

    assert result == "ok"
    assert calls["n"] == 2  # failed once, retried once


def test_transient_error_exhausts_retries_then_raises():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectError("refused")

    settings = InferenceSettings(
        api_base="https://example.test/v1", api_key="test-key", max_retries=1
    )
    http_client = httpx.Client(transport=httpx.MockTransport(handler), base_url=settings.api_base)
    client = InferenceClient(settings=settings, http_client=http_client)

    with pytest.raises(httpx.ConnectError):
        client.complete(
            model="qwen/qwen3-32b",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.0,
            max_tokens=10,
        )
    assert calls["n"] == 2  # first attempt + one retry, both failed


def test_read_timeout_is_not_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ReadTimeout("model too slow")

    settings = InferenceSettings(
        api_base="https://example.test/v1", api_key="test-key", max_retries=3
    )
    http_client = httpx.Client(transport=httpx.MockTransport(handler), base_url=settings.api_base)
    client = InferenceClient(settings=settings, http_client=http_client)

    with pytest.raises(httpx.ReadTimeout):
        client.complete(
            model="qwen/qwen3-32b",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.0,
            max_tokens=10,
        )
    assert calls["n"] == 1  # not retried despite max_retries=3


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


def test_truncated_response_raises_clear_inference_error_not_opaque_typeerror():
    # A thinking model that exhausts max_tokens on its reasoning trace returns
    # content: null with finish_reason "length" — must surface as a clear
    # InferenceError (the more general truncation message, checked first),
    # not an opaque TypeError from json.loads(None) downstream.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "length", "message": {"role": "assistant", "content": None}}
                ]
            },
        )

    client = _client_with_handler(handler)
    with pytest.raises(InferenceError, match="truncated"):
        client.complete(
            model="qwen/qwen3.8-27b",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.4,
            max_tokens=100,
        )


def test_null_content_without_truncation_still_raises_clear_error():
    # Belt-and-suspenders path: content is null but finish_reason isn't
    # "length" (some other provider-side empty-completion case) — still a
    # clear InferenceError, not a downstream TypeError.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"role": "assistant", "content": None}}
                ]
            },
        )

    client = _client_with_handler(handler)
    with pytest.raises(InferenceError, match="no content"):
        client.complete(
            model="qwen/qwen3.8-27b",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.4,
            max_tokens=100,
        )


def test_reasoning_disabled_in_every_request():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = _client_with_handler(handler)
    client.complete(
        model="qwen/qwen3-32b",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.4,
        max_tokens=10,
    )
    assert captured["body"]["reasoning"] == {"enabled": False}


def _fallback_client(statuses_by_model: dict[str, int], seen: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        seen.append(model)
        status = statuses_by_model.get(model, 200)
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "nope"}})
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"value": "' + model + '"}'}}]}
        )

    settings = InferenceSettings(api_base="https://example.test/v1", api_key="k", max_retries=0)
    return InferenceClient(
        settings=settings,
        http_client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url=settings.api_base
        ),
    )


class _Value(BaseModel):
    value: str


def _structured(client, fallbacks):
    return client.complete_structured(
        model="paid",
        system_prompt="s",
        user_content="u",
        temperature=0,
        max_tokens=10,
        response_model=_Value,
        fallback_models=fallbacks,
    )


def test_fallback_on_payment_required_withdrawn_and_rate_limit():
    seen: list[str] = []
    client = _fallback_client({"paid": 402, "gone": 404, "free-a": 429}, seen)

    assert _structured(client, ["gone", "free-a", "free-b"]).value == "free-b"
    assert seen == ["paid", "gone", "free-a", "free-b"]


def test_no_fallback_on_client_error():
    seen: list[str] = []
    client = _fallback_client({"paid": 400}, seen)

    with pytest.raises(httpx.HTTPStatusError):
        _structured(client, ["free-a"])
    assert seen == ["paid"]


def test_last_model_error_propagates(monkeypatch):
    import inference.client as client_module

    monkeypatch.setattr(client_module, "_CHAIN_PAUSE_SECONDS", 0)
    seen: list[str] = []
    client = _fallback_client({"paid": 503, "free-a": 503}, seen)

    with pytest.raises(httpx.HTTPStatusError):
        _structured(client, ["free-a"])
    # Two passes over the chain before giving up.
    assert seen == ["paid", "free-a", "paid", "free-a"]


def test_second_pass_skips_permanently_failed_models(monkeypatch):
    import inference.client as client_module

    monkeypatch.setattr(client_module, "_CHAIN_PAUSE_SECONDS", 0)
    seen: list[str] = []
    busy = {"free-a": 429}
    client = _fallback_client({"paid": 402, **busy}, seen)

    with pytest.raises(httpx.HTTPStatusError):
        _structured(client, ["free-a"])
    assert seen == ["paid", "free-a", "free-a"]


def test_expired_deadline_raises_without_calling_provider():
    import time as _time

    from inference.client import DeadlineExceeded

    seen: list[str] = []
    client = _fallback_client({}, seen)
    client.deadline = _time.monotonic() + 1  # below the minimum call time

    with pytest.raises(DeadlineExceeded):
        _structured(client, ["free-a"])
    assert seen == []


def test_daily_quota_429_stops_the_chain_with_a_clear_error():
    from inference.client import QuotaExhausted

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content)["model"])
        return httpx.Response(
            429,
            json={"error": {"message": "Rate limit exceeded: free-models-per-day"}},
            headers={"X-RateLimit-Reset": "1790380800000"},
        )

    settings = InferenceSettings(api_base="https://example.test/v1", api_key="k", max_retries=0)
    client = InferenceClient(
        settings=settings,
        http_client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url=settings.api_base
        ),
    )
    with pytest.raises(QuotaExhausted, match="Resets at"):
        _structured(client, ["free-a", "free-b"])
    assert len(seen) == 1
