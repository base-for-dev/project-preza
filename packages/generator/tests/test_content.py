"""End-to-end test of `generate_content` with the HTTP layer mocked.

    uv run pytest packages/generator
"""

from __future__ import annotations

import json

import httpx
from design_system import LayoutPattern, ShapeSummary
from generator import DeckContent, Outline, SlideIntent, generate_content
from inference import InferenceClient, InferenceSettings


def _outline() -> Outline:
    return Outline(
        slides=[
            SlideIntent(
                role="Title Slide",
                intent="open with the deck's core claim",
                summary="Switching to renewable procurement cuts costs 12% by 2027.",
            ),
            SlideIntent(
                role="Two Content",
                intent="lay out the cost comparison",
                summary="Renewable contracts beat fossil rates within 18 months.",
            ),
        ]
    )


def _patterns() -> list[LayoutPattern]:
    return [
        LayoutPattern(
            layout_name="Title Slide",
            slide_count=1,
            shape_summaries=[
                ShapeSummary(
                    kind="text_box",
                    count_min=1,
                    count_max=1,
                    count_mean=1.0,
                    left_range=(0.1, 0.1),
                    top_range=(0.1, 0.1),
                    right_range=(0.9, 0.9),
                    bottom_range=(0.3, 0.3),
                )
            ],
        ),
        LayoutPattern(
            layout_name="Two Content",
            slide_count=3,
            shape_summaries=[
                ShapeSummary(
                    kind="text_box",
                    count_min=2,
                    count_max=2,
                    count_mean=2.0,
                    left_range=(0.05, 0.5),
                    top_range=(0.2, 0.2),
                    right_range=(0.45, 0.95),
                    bottom_range=(0.9, 0.9),
                ),
                ShapeSummary(
                    kind="table",
                    count_min=0,
                    count_max=1,
                    count_mean=0.3,
                    left_range=(0.1, 0.1),
                    top_range=(0.3, 0.3),
                    right_range=(0.9, 0.9),
                    bottom_range=(0.8, 0.8),
                ),
            ],
        ),
    ]


def test_generate_content_parses_response_and_sends_full_prompt():
    captured: dict = {}

    mocked_content = {
        "slides": [
            {
                "role": "Title Slide",
                "title": "Switching to renewable procurement cuts costs 12% by 2027.",
                "bullets": [],
                "body": "A short pitch to the board on renewable procurement.",
                "table": None,
                "image_brief": None,
            },
            {
                "role": "Two Content",
                "title": "Renewable contracts beat fossil rates within 18 months.",
                "bullets": [
                    "Fixed-rate contracts hedge against volatility",
                    "Break-even hits month 18",
                ],
                "body": None,
                "table": [
                    ["Year", "Fossil", "Renewable"],
                    ["1", "$1.2M", "$1.4M"],
                    ["2", "$1.3M", "$1.1M"],
                ],
                "image_brief": None,
            },
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(mocked_content)}}]},
        )

    settings = InferenceSettings(api_base="https://example.test/v1", api_key="test-key")
    http_client = httpx.Client(transport=httpx.MockTransport(handler), base_url=settings.api_base)
    client = InferenceClient(settings=settings, http_client=http_client)

    brief = "Pitch renewable energy procurement to the board, focus on cost savings."
    outline = _outline()
    patterns = _patterns()

    result = generate_content(outline, patterns, brief, client=client)

    assert result == DeckContent.model_validate(mocked_content)

    sent_messages = captured["body"]["messages"]
    system_message = sent_messages[0]["content"]
    user_message = sent_messages[1]["content"]

    assert "content" in system_message.lower()
    assert brief in user_message
    for slide in outline.slides:
        assert slide.role in user_message
        assert slide.intent in user_message
        assert slide.summary in user_message
    # Pattern shape info made it into the prompt, not dropped on the floor.
    assert "text_box" in user_message
    assert "table" in user_message
    assert captured["body"]["response_format"] == {"type": "json_object"}


def test_generate_content_without_api_key_raises_runtime_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not send a request without an API key")

    settings = InferenceSettings(api_base="https://example.test/v1", api_key=None)
    http_client = httpx.Client(transport=httpx.MockTransport(handler), base_url=settings.api_base)
    client = InferenceClient(settings=settings, http_client=http_client)

    import pytest

    with pytest.raises(RuntimeError, match="INFERENCE_API_KEY"):
        generate_content(_outline(), _patterns(), "brief", client=client)
