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


def test_outline_is_moved_onto_the_templates_cover_layout():
    from design_system import LayoutPattern, SlotSummary
    from generator.outline import Outline, SlideIntent, _open_on_the_cover

    def pat(name: str, first: int, **slots) -> LayoutPattern:
        return LayoutPattern(
            layout_name=name,
            slide_count=1,
            shape_summaries=[],
            first_slide_index=first,
            slots=SlotSummary(**slots),
        )

    patterns = [
        pat("Bare picture", 0),  # cannot carry a title: never a cover
        pat("Cover", 1, has_title=True, body_slots=1),
        pat("Second cover", 2, has_title=True, body_slots=1),
        pat("Content", 5, has_title=True, body_slots=1),
    ]
    outline = Outline(slides=[SlideIntent(role="Content", intent="i", summary="s")])
    _open_on_the_cover(outline, patterns)
    assert outline.slides[0].role == "Cover"

    already = Outline(slides=[SlideIntent(role="Cover", intent="i", summary="s")])
    _open_on_the_cover(already, patterns)
    assert already.slides[0].role == "Cover"

    _open_on_the_cover(outline, ["Content", "Cover"])  # names only: nothing known, untouched
    assert outline.slides[0].role == "Cover"


def test_layouts_with_nowhere_to_put_text_are_not_offered():
    from design_system import LayoutPattern, SlotSummary
    from generator.outline import _fillable_only

    def pat(name: str, **slots) -> LayoutPattern:
        return LayoutPattern(
            layout_name=name, slide_count=1, shape_summaries=[], slots=SlotSummary(**slots)
        )

    bare, real = pat("Bare"), pat("Real", has_title=True)
    assert _fillable_only([bare, real]) == [real]
    assert _fillable_only([bare]) == [bare]  # never leave the model with nothing
    assert _fillable_only(["a", "b"]) == ["a", "b"]  # names only: nothing known


def test_split_sections_on_dash_lines_only():
    from generator.outline import split_sections

    text = "Intro about us\n---\nThe problem\n\n-----\nOur solution"
    assert split_sections(text) == ["Intro about us", "The problem", "Our solution"]
    assert split_sections("no breaks - here -- at all") == []


def test_sections_fix_slide_count_and_reach_the_prompt():
    from generator.outline import Outline, SlideIntent, generate_outline

    captured = {}

    class Client:
        def complete_structured(self, **kwargs):
            captured["prompt"] = kwargs["user_content"]
            return Outline(
                slides=[SlideIntent(role="A", intent="i", summary=f"s{i}") for i in range(2)]
            )

    generate_outline(
        "brief",
        10,
        ["A"],
        sections=["Первая часть", "Вторая часть"],
        text_mode="preserve",
        client=Client(),
    )

    prompt = captured["prompt"]
    assert "Target slide count: 2" in prompt
    assert "2. Вторая часть" in prompt
    assert "Text mode: preserve" in prompt


def test_finalize_outline_repairs_a_user_edited_plan():
    from generator.outline import Outline, SlideIntent, finalize_outline

    edited = Outline(
        slides=[
            SlideIntent(role="A", intent="i", summary="s", seconds=0),
            SlideIntent(role="nonexistent", intent="i", summary="s", seconds=0),
        ]
    )
    result = finalize_outline(edited, ["A", "B"], duration_seconds=120)

    assert [s.role for s in result.slides] == ["A", "A"]
    assert sum(s.seconds for s in result.slides) == 120


def test_contact_slides_offered_only_with_contact_details():
    from design_system import LayoutPattern
    from generator.outline import _without_contact_slides, has_contact_details

    patterns = [
        LayoutPattern(layout_name=n, slide_count=1, shape_summaries=[])
        for n in ("title-01", "contacts-12", "team-05")
    ]
    kept = _without_contact_slides(patterns, "Про кошек")
    assert [p.layout_name for p in kept] == ["title-01", "team-05"]
    briefs = ("Пишите: anna@cats.ru", "Тел. +7 912 345-67-89", "Канал t.me/cats", "Сайт cats.ru")
    for brief in briefs:
        assert has_contact_details(brief)
        assert len(_without_contact_slides(patterns, brief)) == 3
