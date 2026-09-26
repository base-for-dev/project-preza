"""uv run pytest packages/brand"""

import re

from brand import build_slide_catalog
from brand.catalog import catalog_rows
from design_system import SlideCatalog, SlideCatalogEntry
from ir_schema import Deck, Paragraph, Slide, TextBoxShape, TextRun


def _text(text: str) -> TextBoxShape:
    return TextBoxShape(
        shape_id=1, name="t", z_order=0, left=0, top=0, width=1_000_000, height=500_000,
        paragraphs=[Paragraph(runs=[TextRun(text=text)])],
    )


def _deck(n: int) -> Deck:
    return Deck(
        slide_width=9_144_000,
        slide_height=6_858_000,
        slides=[Slide(index=i, layout_name="L", shapes=[_text(f"текст {i}")]) for i in range(n)],
    )


class FakeClient:
    def __init__(self):
        self.prompts: list[str] = []

    def complete_structured(self, **kwargs):
        prompt = kwargs["user_content"]
        self.prompts.append(prompt)
        numbers = [int(n) for n in re.findall(r"^#(\d+) ", prompt, flags=re.M)]
        return SlideCatalog(
            entries=[
                SlideCatalogEntry(index=n, usable=n != 1, purpose="title" if n == 2 else "content")
                for n in numbers
            ]
        )


def test_rows_are_one_based_and_show_text():
    rows = catalog_rows(_deck(2))
    assert rows.splitlines()[0].startswith("#1 layout: 'L'")
    assert "текст 1" in rows.splitlines()[1]


def test_catalog_maps_one_based_reply_to_slide_index_and_batches():
    client = FakeClient()

    catalog = build_slide_catalog(_deck(25), client=client)  # type: ignore[arg-type]

    assert len(client.prompts) == 2  # batches of 20
    assert len(catalog.entries) == 25
    first, second = catalog.entries[0], catalog.entries[1]
    assert (first.index, first.usable) == (0, False)  # "#1" in the prompt
    assert (second.index, second.purpose) == (1, "title")  # "#2" in the prompt
