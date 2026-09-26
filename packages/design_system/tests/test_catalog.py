"""uv run pytest packages/design_system"""

from design_system import SlideCatalog, SlideCatalogEntry, apply_catalog, extract_design_system
from ir_schema import Deck, Slide


def _deck(n: int) -> Deck:
    return Deck(
        slide_width=9_144_000,
        slide_height=6_858_000,
        slides=[Slide(index=i, layout_name="Blank") for i in range(n)],
    )


def test_apply_catalog_drops_unusable_and_names_roles_by_purpose():
    catalog = SlideCatalog(
        entries=[
            SlideCatalogEntry(index=0, usable=False, purpose="content"),
            SlideCatalogEntry(index=1, purpose="title", description="team and task name"),
            SlideCatalogEntry(index=2, purpose="Team!", description="member cards"),
        ]
    )

    deck, descriptions = apply_catalog(_deck(3), catalog)

    assert [s.layout_name for s in deck.slides] == ["title-02", "team-03"]
    assert descriptions == {"title-02": "team and task name", "team-03": "member cards"}
    # Each usable slide becomes its own pattern, so the outline picks exact slides.
    assert [p.layout_name for p in extract_design_system(deck).patterns] == ["title-02", "team-03"]


def test_missing_entries_stay_usable_and_unknown_purpose_is_content():
    catalog = SlideCatalog(entries=[SlideCatalogEntry(index=0, purpose="hero-banner")])

    deck, _ = apply_catalog(_deck(2), catalog)

    assert [s.layout_name for s in deck.slides] == ["content-01", "content-02"]


def test_all_unusable_catalog_is_ignored():
    catalog = SlideCatalog(entries=[SlideCatalogEntry(index=i, usable=False) for i in range(2)])

    deck, _ = apply_catalog(_deck(2), catalog)

    assert len(deck.slides) == 2


def test_apply_catalog_never_mutates_input():
    original = _deck(1)
    apply_catalog(original, SlideCatalog(entries=[SlideCatalogEntry(index=0, purpose="title")]))
    assert original.slides[0].layout_name == "Blank"
