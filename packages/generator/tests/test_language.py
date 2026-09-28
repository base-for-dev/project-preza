"""uv run pytest packages/generator"""

from generator.language import deck_language, is_in, language_line
from generator.outline import Outline, SlideIntent, generate_outline


def test_deck_language_from_brief():
    assert deck_language("Презентация про кошек") == "Russian"
    assert deck_language("Pitch deck for a fintech startup") == "English"
    assert deck_language("Питч для Series A: наш API и SDK") == "Russian"
    assert deck_language("ok") is None


def test_is_in_allows_proper_nouns():
    assert is_in("Russian", "project-preza собирает колоду из .pptx")
    assert not is_in("Russian", "Cats: the ultimate companions")
    assert is_in("Russian", "")


def test_outline_prompt_states_language_and_retries_on_drift():
    prompts: list[str] = []

    class Client:
        def complete_structured(self, **kwargs):
            prompts.append(kwargs["user_content"])
            if len(prompts) == 1:
                summaries = ["Cats are great", "Dogs are loyal"]
            else:
                summaries = ["Кошки прекрасны", "Собаки преданны"]
            return Outline(
                slides=[SlideIntent(role="A", intent="i", summary=s) for s in summaries]
            )

    outline = generate_outline("Презентация про кошек", 2, ["A"], client=Client())

    assert language_line("Russian") in prompts[0]
    assert len(prompts) == 2 and "not in Russian" in prompts[1]
    assert [s.summary for s in outline.slides] == ["Кошки прекрасны", "Собаки преданны"]
