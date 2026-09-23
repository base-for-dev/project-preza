"""Invented-figure repair pass in `generate_content`.

uv run pytest packages/generator
"""

from __future__ import annotations

from generator import DeckContent, Outline, SlideIntent, generate_content
from generator.content import SlideContent, _ungrounded_by_slide


class _FakeClient:
    def __init__(self, drafts: list[DeckContent]):
        self.drafts = drafts
        self.prompts: list[str] = []

    def complete_structured(self, **kwargs):
        self.prompts.append(kwargs["user_content"])
        return self.drafts[len(self.prompts) - 1]


def _deck(text: str) -> DeckContent:
    return DeckContent(slides=[SlideContent(role="A", title="T", bullets=[text])])


def _outline() -> Outline:
    return Outline(slides=[SlideIntent(role="A", intent="i", summary="s")])


def test_grounded_figures_are_not_flagged():
    assert _ungrounded_by_slide(_deck("Рост 40%"), "рынок растёт на 40%") == {}


def test_invented_figure_is_flagged_per_slide():
    assert _ungrounded_by_slide(_deck("Рост 35%"), "рынок растёт") == {1: {"35"}}


def test_invented_figures_trigger_one_corrective_retry():
    client = _FakeClient([_deck("Рост 35%"), _deck("Рынок стабильно растёт")])
    result = generate_content(_outline(), [], "рынок растёт", client=client)  # type: ignore[arg-type]
    assert len(client.prompts) == 2
    assert "35" in client.prompts[1]
    assert result.slides[0].bullets == ["Рынок стабильно растёт"]


def test_clean_draft_makes_a_single_call():
    client = _FakeClient([_deck("Рынок растёт")])
    generate_content(_outline(), [], "рынок растёт", client=client)  # type: ignore[arg-type]
    assert len(client.prompts) == 1


def test_retry_that_is_no_better_keeps_the_original():
    first, second = _deck("Рост 35%"), _deck("Рост 35% и 40%")
    client = _FakeClient([first, second])
    result = generate_content(_outline(), [], "рынок растёт", client=client)  # type: ignore[arg-type]
    assert result is first
