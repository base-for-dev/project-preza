"""End-to-end test of `generate_content` with the HTTP layer mocked.

uv run pytest packages/generator
"""

from __future__ import annotations

import json

import httpx
from design_system import LayoutPattern, ShapeSummary, SlotSummary
from generator import DeckContent, Outline, SlideIntent, generate_content
from generator.content import SlideContent
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

    brief = (
        "Pitch renewable energy procurement to the board, focus on cost savings: "
        "12% by 2027, break-even at month 18, costs $1.2M $1.4M $1.3M $1.1M."
    )
    outline = _outline()
    patterns = _patterns()

    result = generate_content(outline, patterns, brief, parallel=False, client=client)

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
    # Hand-built patterns carry no slot structure, so the prompt must say so
    # honestly rather than silently omitting the budget.
    assert "structure unknown" in user_message
    assert captured["body"]["response_format"] == {"type": "json_object"}


def _prompt_for(slots_by_role: dict[str, SlotSummary]) -> str:
    from generator.content import _build_user_prompt

    outline = _outline()
    return _build_user_prompt("brief", outline, [slots_by_role.get(s.role) for s in outline.slides])


def test_card_slide_prompt_demands_exactly_n_items():
    prompt = _prompt_for(
        {"Two Content": SlotSummary(has_title=True, card_slots=3), "Title Slide": SlotSummary()}
    )
    assert "3 parallel cards" in prompt
    assert "EXACTLY 3 items" in prompt


def test_body_slide_prompt_allows_bullets_or_body():
    prompt = _prompt_for({"Two Content": SlotSummary(has_title=True, body_slots=1)})
    assert "one text area" in prompt
    assert "OR" in prompt


def test_table_and_picture_permissions_follow_structure():
    with_both = _prompt_for(
        {"Two Content": SlotSummary(has_title=True, body_slots=1, has_table=True, has_picture=True)}
    )
    assert '"table": allowed' in with_both
    assert '"image_brief": required' in with_both
    assert '"image_query": required' in with_both

    neither = _prompt_for({"Two Content": SlotSummary(has_title=True, body_slots=1)})
    assert '"table": must be null' in neither
    assert '"image_brief": must be null' in neither
    assert '"image_query": must be null' in neither


def test_slide_content_coerces_null_bullets_to_empty_list():
    # Some providers emit "bullets": null for a slide with no bullets instead
    # of [] despite the schema — this must parse, not raise a validation error.
    parsed = SlideContent.model_validate(
        {"role": "Title Slide", "title": "A title", "bullets": None}
    )
    assert parsed.bullets == []


def test_generate_content_without_api_key_raises_runtime_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not send a request without an API key")

    settings = InferenceSettings(api_base="https://example.test/v1", api_key=None)
    http_client = httpx.Client(transport=httpx.MockTransport(handler), base_url=settings.api_base)
    client = InferenceClient(settings=settings, http_client=http_client)

    import pytest

    with pytest.raises(RuntimeError, match="INFERENCE_API_KEY"):
        generate_content(_outline(), _patterns(), "brief", client=client)


class _PerSlideClient:
    """Fake client answering each per-slide call with that slide's own content."""

    def __init__(self, fail_first_for: set[int] | None = None):
        self.prompts: list[str] = []
        self.fail_first_for = set(fail_first_for or ())

    def complete_structured(self, **kwargs):
        import re

        prompt = kwargs["user_content"]
        self.prompts.append(prompt)
        numbers = re.search(r"Write ONLY slides ([\d, ]+) of", prompt).group(1)
        ns = [int(n) for n in numbers.split(",")]
        if self.fail_first_for & set(ns):
            self.fail_first_for -= set(ns)
            raise RuntimeError("transient")
        return DeckContent(
            slides=[{"role": "WRONG", "title": f"T{n}", "speaker_notes": f"notes {n}"} for n in ns]
        )


def test_parallel_content_writes_each_slide_in_order_with_notes():
    client = _PerSlideClient()
    outline = _outline()

    result = generate_content(outline, _patterns(), "brief", brand="Brand: X", client=client)

    assert [s.title for s in result.slides] == ["T1", "T2"]
    assert [s.speaker_notes for s in result.slides] == ["notes 1", "notes 2"]
    # Role is structural — restored from the outline, never the model's.
    assert [s.role for s in result.slides] == [s.role for s in outline.slides]
    assert all("Brand: X" in p for p in client.prompts)
    # Every call still sees the whole outline.
    assert all(outline.slides[1].summary in p for p in client.prompts)


def test_parallel_content_retries_a_failed_group_once():
    client = _PerSlideClient(fail_first_for={2})

    result = generate_content(_outline(), _patterns(), "brief", client=client)

    assert [s.title for s in result.slides] == ["T1", "T2"]
    assert len(client.prompts) == 3


def test_parallel_content_uses_at_most_three_calls():
    from generator.content import CONTENT_CALLS
    from generator.outline import Outline, SlideIntent

    outline = Outline(
        slides=[SlideIntent(role="Two Content", intent=f"i{n}", summary=f"s{n}") for n in range(8)]
    )
    client = _PerSlideClient()

    result = generate_content(outline, _patterns(), "brief", client=client)

    assert [s.title for s in result.slides] == [f"T{n}" for n in range(1, 9)]
    assert len(client.prompts) == CONTENT_CALLS == 3


def test_notes_budget_follows_slide_seconds():
    from generator.content import _build_user_prompt

    outline = _outline()
    outline.slides[0].seconds = 60
    prompt = _build_user_prompt("b", outline, [None, None], only_slides=[0])

    # 120 words for 60 s, asked for x1.1 to offset the models' undershoot.
    assert '"speaker_notes": 132 words, at least 119 (spoken over ~60 s)' in prompt
    # Only the target slide carries fill rules.
    assert prompt.count("structure unknown") == 1


def test_budget_card_hint_scales_with_card_size():
    from generator.content import _slide_budget

    small = SlotSummary(has_title=True, card_slots=3, card_chars=35)
    assert "at most 35 characters — the card is small" in _slide_budget(small)

    large = SlotSummary(has_title=True, card_slots=2, card_chars=300)
    # Big cards ask for a sentence (capped), not a bare heading.
    assert "one full sentence of 8-15 words, at most 200 characters" in _slide_budget(large)


def test_two_field_cards_ask_for_heading_dash_text():
    from generator.content import _slide_budget

    slots = SlotSummary(
        has_title=True, card_slots=5, card_fields=2, card_heading_chars=20, card_chars=50
    )
    text = _slide_budget(slots)
    assert 'EXACTLY 5 items' in text
    assert '"Heading — text"' in text
    assert "≤ 20 chars" in text


def test_expired_deadline_skips_repair_calls_but_keeps_deterministic_fixes():
    import time as _time

    from generator.content import generate_content

    class Client:
        def __init__(self):
            self.calls = 0

        def complete_structured(self, **kwargs):
            self.calls += 1
            return DeckContent(
                slides=[
                    {"role": "Two Content", "title": "Рынок растёт", "bullets": ["Рост 35%", "Спрос"]}
                ]
            )

    client = Client()
    from generator.outline import Outline, SlideIntent

    outline = Outline(slides=[SlideIntent(role="Two Content", intent="i", summary="s")])
    result = generate_content(
        outline, _patterns(), "рынок растёт", deadline=_time.monotonic(), client=client
    )

    assert client.calls == 1  # the draft only — no corrective or string-repair calls
    # The deterministic fallback still removes the invented figure.
    assert all("35" not in b for b in result.slides[0].bullets)


def test_group_that_misses_the_deadline_falls_back_to_outline_slides():
    import time as _time

    from generator.content import generate_content
    from generator.outline import Outline, SlideIntent
    from inference import DeadlineExceeded

    class Client:
        def complete_structured(self, **kwargs):
            if "Write ONLY slides 1" in kwargs["user_content"]:
                return DeckContent(slides=[{"role": "Two Content", "title": "Готово"}])
            raise DeadlineExceeded("late")

    outline = Outline(
        slides=[SlideIntent(role="Two Content", intent="i", summary=f"Тезис {n}") for n in range(3)]
    )
    result = generate_content(
        outline, _patterns(), "b", deadline=_time.monotonic() + 600, client=Client()
    )

    assert [s.title for s in result.slides] == ["Готово", "Тезис 1", "Тезис 2"]


def test_all_groups_missing_the_deadline_is_an_error():
    import time as _time

    import pytest

    from generator.content import generate_content
    from generator.outline import Outline, SlideIntent
    from inference import DeadlineExceeded

    class Client:
        def complete_structured(self, **kwargs):
            raise DeadlineExceeded("late")

    outline = Outline(slides=[SlideIntent(role="Two Content", intent="i", summary="s")])
    with pytest.raises(DeadlineExceeded):
        generate_content(outline, _patterns(), "b", deadline=_time.monotonic() + 600, client=Client())
