"""End-to-end test of `generate_outline` with the HTTP layer mocked.

    uv run pytest packages/generator
"""

from __future__ import annotations

import json

import httpx
from generator import Outline, generate_outline
from inference import InferenceClient, InferenceSettings


def test_generate_outline_parses_response_and_sends_full_prompt():
    captured: dict = {}

    mocked_outline = {
        "slides": [
            {
                "role": "Title Slide",
                "intent": "open with the deck's core claim",
                "summary": "Switching to renewable procurement cuts costs 12% by 2027.",
            },
            {
                "role": "Section Header",
                "intent": "set up the problem",
                "summary": "Energy costs are the largest uncontrolled line item in opex.",
            },
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(mocked_outline)}}]},
        )

    settings = InferenceSettings(api_base="https://example.test/v1", api_key="test-key")
    http_client = httpx.Client(transport=httpx.MockTransport(handler), base_url=settings.api_base)
    client = InferenceClient(settings=settings, http_client=http_client)

    brief = "Pitch renewable energy procurement to the board, focus on cost savings."
    patterns = ["Title Slide", "Section Header", "Two Content", "Comparison"]

    result = generate_outline(brief, slide_count=2, available_patterns=patterns, client=client)

    assert result == Outline.model_validate(mocked_outline)

    sent_messages = captured["body"]["messages"]
    system_message = sent_messages[0]["content"]
    user_message = sent_messages[1]["content"]

    assert "outline" in system_message.lower()
    assert brief in user_message
    for pattern in patterns:
        assert pattern in user_message
    assert "2" in user_message  # slide_count made it into the prompt
    assert captured["body"]["response_format"] == {"type": "json_object"}


def test_generate_outline_without_api_key_raises_runtime_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not send a request without an API key")

    settings = InferenceSettings(api_base="https://example.test/v1", api_key=None)
    http_client = httpx.Client(transport=httpx.MockTransport(handler), base_url=settings.api_base)
    client = InferenceClient(settings=settings, http_client=http_client)

    import pytest

    with pytest.raises(RuntimeError, match="INFERENCE_API_KEY"):
        generate_outline("brief", slide_count=3, available_patterns=["Title Slide"], client=client)


# --- role resolution --------------------------------------------------------
# Regression: the model echoed the whole catalog line ("19_Заголовок (template
# has 3) — title + 3 cards") as `role`. A strict "not in valid set -> first
# layout" clamp then silently turned an excellent, varied outline into 8 copies
# of the first layout. Roles must be *recovered*, not clobbered.

from generator.outline import _resolve_role  # noqa: E402

_NAMES = ["1_Контент", "11_Контент", "19_Заголовок", "15_Титульный слайд"]


def test_resolve_role_exact_match():
    assert _resolve_role("19_Заголовок", _NAMES) == "19_Заголовок"


def test_resolve_role_recovers_name_from_echoed_catalog_line():
    echoed = "19_Заголовок (template has 3) — title + 3 parallel cards"
    assert _resolve_role(echoed, _NAMES) == "19_Заголовок"


def test_resolve_role_strips_quotes():
    assert _resolve_role('"15_Титульный слайд"', _NAMES) == "15_Титульный слайд"


def test_resolve_role_prefers_longest_name_not_shorter_prefix():
    # "1_Контент" is a prefix-substring of "11_Контент"; must not steal it.
    assert _resolve_role("11_Контент (template has 1)", _NAMES) == "11_Контент"


def test_resolve_role_unrecognisable_falls_back_to_first_layout():
    assert _resolve_role("totally made up", _NAMES) == "1_Контент"


def test_catalog_line_quotes_the_name_and_describes_structure():
    from design_system import LayoutPattern, SlotSummary
    from generator.outline import _catalog_line

    line = _catalog_line(
        LayoutPattern(
            layout_name="19_Заголовок",
            slide_count=3,
            shape_summaries=[],
            slots=SlotSummary(has_title=True, card_slots=3),
        )
    )
    assert line.startswith('- "19_Заголовок"')
    assert "3 parallel cards" in line
