"""Tests for `inference.skills.load_skill` against a real skill directory.

uv run pytest packages/inference
"""

from __future__ import annotations

import pytest
from inference import load_skill


def test_load_skill_parses_outline_generation():
    skill = load_skill("outline-generation")

    assert skill.name == "outline-generation"
    assert "outline" in skill.prompt.lower()
    # model is a product/cost choice that changes independently of parsing
    # correctness (e.g. temporary free-tier swaps — see MODELS.md) — assert
    # shape, not the live repo's current pick.
    assert isinstance(skill.model, str) and skill.model
    assert skill.temperature == pytest.approx(0.4)
    # max_tokens is a tuning knob (raised after free-tier truncation on a
    # 10-slide outline — see client.py's finish_reason check), same
    # "assert shape, not the live value" reasoning as `model` above.
    assert isinstance(skill.max_tokens, int) and skill.max_tokens > 0


def test_load_skill_missing_directory_raises():
    with pytest.raises(FileNotFoundError):
        load_skill("does-not-exist")


def test_load_skill_missing_config_field_raises(tmp_path):
    skill_dir = tmp_path / "broken-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("prompt body")
    (skill_dir / "config.yaml").write_text("model: some-model\ntemperature: 0.5\n")

    with pytest.raises(ValueError, match="max_tokens"):
        load_skill("broken-skill", skills_dir=tmp_path)
