"""Surgical string repair for invented figures and over-long text.

uv run pytest packages/generator
"""

from __future__ import annotations

from design_system import SlotSummary
from generator.content import DeckContent, SlideContent, _repair_strings
from generator.textfix import Fix, Rewrites, rewrite_strings


class _Client:
    def __init__(self, items: list[str] | Exception):
        self.items = items
        self.calls = 0

    def complete_structured(self, **kwargs):
        self.calls += 1
        if isinstance(self.items, Exception):
            raise self.items
        assert kwargs["response_model"] is Rewrites
        return Rewrites(items=self.items)


def _slide(**kw) -> SlideContent:
    return SlideContent(role="A", **kw)


def test_invented_figure_in_a_title_is_rewritten():
    content = DeckContent(slides=[_slide(title="Рынок вырос на 35%")])
    client = _Client(["Рынок заметно вырос"])
    _repair_strings(content, "рынок растёт", [None], client)  # type: ignore[arg-type]
    assert content.slides[0].title == "Рынок заметно вырос"


def test_rewrite_that_still_has_the_figure_is_rejected():
    content = DeckContent(slides=[_slide(title="Рынок вырос на 35%")])
    client = _Client(["Рынок вырос на 35 процентов"])
    _repair_strings(content, "рынок растёт", [None], client)  # type: ignore[arg-type]
    assert content.slides[0].title == "Рынок вырос на 35%"


def test_over_long_card_is_shortened_but_count_is_kept():
    slot = SlotSummary(card_slots=2, card_chars=20)
    content = DeckContent(
        slides=[_slide(title="T", bullets=["Очень длинная подпись к первой карточке", "Ок"])]
    )
    client = _Client(["Короткая подпись"])
    _repair_strings(content, "", [slot], client)  # type: ignore[arg-type]
    assert content.slides[0].bullets == ["Короткая подпись", "Ок"]


def test_no_violations_makes_no_call():
    content = DeckContent(slides=[_slide(title="Рынок растёт", bullets=["Ок"])])
    client = _Client(["x"])
    _repair_strings(content, "рынок растёт", [None], client)  # type: ignore[arg-type]
    assert client.calls == 0


def test_failed_call_returns_the_originals():
    fixes = [Fix(text="Рост 35%", forbidden_figures=["35"])]
    assert rewrite_strings(fixes, _Client(RuntimeError("boom"))) == ["Рост 35%"]  # type: ignore[arg-type]


def test_wrong_item_count_returns_the_originals():
    fixes = [Fix(text="а"), Fix(text="б")]
    assert rewrite_strings(fixes, _Client(["только одно"])) == ["а", "б"]  # type: ignore[arg-type]


def test_bullets_are_cut_to_what_the_text_area_holds():
    from generator.content import _fit_bullet_count

    slot = SlotSummary(body_slots=1, body_lines=2, body_chars_per_line=40)
    content = DeckContent(slides=[_slide(title="T", bullets=["a", "b", "c", "d"])])
    _fit_bullet_count(content, [slot])
    assert content.slides[0].bullets == ["a", "b"]


def test_invented_figure_in_a_table_cell_is_rewritten():
    content = DeckContent(
        slides=[_slide(title="T", table=[["Город", "Рост"], ["Москва", "12 городов"]])]
    )
    client = _Client(["несколько городов"])
    _repair_strings(content, "", [None], client)  # type: ignore[arg-type]
    assert content.slides[0].table == [["Город", "Рост"], ["Москва", "несколько городов"]]


def test_wordy_bullet_is_shortened():
    long = " ".join(["слово"] * 20)
    content = DeckContent(slides=[_slide(title="T", bullets=[long])])
    client = _Client(["Коротко и по делу"])
    _repair_strings(content, "", [None], client)  # type: ignore[arg-type]
    assert content.slides[0].bullets == ["Коротко и по делу"]
