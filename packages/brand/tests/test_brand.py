"""uv run pytest packages/brand"""

from __future__ import annotations

from brand import (
    BrandContext,
    BrandEntity,
    BrandExtraction,
    BrandVoice,
    build_brand_context,
    merge_extractions,
)


class FakeClient:
    def __init__(self, result: BrandExtraction):
        self.result = result
        self.calls: list[str] = []

    def complete_structured(self, **kwargs):
        self.calls.append(kwargs["user_content"])
        return self.result


def test_build_sorts_files_by_kind_and_extracts_voice(tmp_path):
    (tmp_path / "brandbook.md").write_text("Хакатон ЛЦТ — главный конкурс.", encoding="utf-8")
    (tmp_path / "logo-main.png").write_bytes(b"png")
    (tmp_path / "hero.jpg").write_bytes(b"jpg")
    (tmp_path / "Inter-Bold.ttf").write_bytes(b"ttf")
    files = sorted(tmp_path.iterdir())
    client = FakeClient(
        BrandExtraction(
            entities=[BrandEntity(name="ЛЦТ", kind="event")],
            voice=BrandVoice(tone=["коротко"]),
        )
    )

    ctx = build_brand_context("p1", "ЛЦТ", files, client=client)

    assert ctx.logos == ["logo-main.png"]
    assert ctx.images == ["hero.jpg"]
    assert ctx.font_files == ["Inter-Bold.ttf"]
    assert "Inter" in ctx.fonts
    assert ctx.documents == ["brandbook.md"]
    assert ctx.entities[0].name == "ЛЦТ"
    assert "главный конкурс" in client.calls[0]


def test_build_without_text_makes_no_llm_call(tmp_path):
    (tmp_path / "logo.png").write_bytes(b"png")
    client = FakeClient(BrandExtraction())

    ctx = build_brand_context("p", "X", [tmp_path / "logo.png"], client=client)

    assert client.calls == []
    assert ctx.entities == []


def test_merge_dedupes_entities_and_voice():
    a = BrandExtraction(
        entities=[BrandEntity(name="Preza", description="")],
        voice=BrandVoice(tone=["Коротко", "по делу"]),
    )
    b = BrandExtraction(
        entities=[BrandEntity(name="preza", description="генератор колод")],
        voice=BrandVoice(tone=["коротко"]),
    )

    merged = merge_extractions([a, b])

    assert len(merged.entities) == 1
    assert merged.entities[0].description == "генератор колод"
    assert merged.voice.tone == ["Коротко", "по делу"]


def test_prompt_text_is_compact_and_lists_names():
    ctx = BrandContext(
        id="p",
        name="ЛЦТ",
        entities=[BrandEntity(name=f"E{i}", description="d" * 100) for i in range(40)],
        voice=BrandVoice(tone=["коротко"], signature_phrases=["Код решает"]),
    )
    text = ctx.prompt_text()
    assert text.startswith("Brand: ЛЦТ")
    assert "Код решает" in text or len(text) == 2_000
    assert len(text) <= 2_000


def test_structure_longest_wins_and_is_in_prompt():
    merged = merge_extractions(
        [BrandExtraction(structure=["A"]), BrandExtraction(structure=["Проблема", "Решение", "Демо"])]
    )
    assert merged.structure == ["Проблема", "Решение", "Демо"]

    ctx = BrandContext(id="p", name="X", structure=merged.structure)
    assert "1. Проблема" in ctx.prompt_text()


def test_template_guidance_is_not_brand_voice():
    ctx = BrandContext(
        id="p",
        name="X",
        voice=BrandVoice(
            signature_phrases=["Привет, участник хакатона!", "Удачи!", "Код решает", "Insert your logo"]
        ),
    )
    text = ctx.prompt_text()
    assert "Код решает" in text
    assert "Привет" not in text and "Удачи" not in text and "Insert" not in text
