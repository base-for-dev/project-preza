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
    (skill_dir / "config.yaml").write_text("version: 0.1.0\nmodel: some-model\ntemperature: 0.5\n")

    with pytest.raises(ValueError, match="max_tokens"):
        load_skill("broken-skill", skills_dir=tmp_path)


def test_every_skill_has_a_semantic_version():
    from inference import list_skills

    skills = list_skills()
    assert skills
    assert all(s.version.count(".") == 2 for s in skills)


def test_a_bad_version_is_rejected(tmp_path):
    skill_dir = tmp_path / "s"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("prompt")
    (skill_dir / "config.yaml").write_text(
        "version: one\nmodel: m\ntemperature: 0\nmax_tokens: 1\n"
    )
    with pytest.raises(ValueError, match="MAJOR.MINOR.PATCH"):
        load_skill("s", skills_dir=tmp_path)


def test_a_skill_that_changed_without_a_version_bump_fails_the_lock():
    """Edit a prompt or a model setting -> bump `version:` -> `python scripts/lock_skills.py`."""
    import json
    from pathlib import Path

    from inference import content_hash, list_skills

    lock = json.loads(
        (Path(__file__).resolve().parents[3] / "skills" / "skills.lock.json").read_text(
            encoding="utf-8"
        )
    )
    for skill in list_skills():
        locked = lock.get(skill.name)
        assert locked, f"{skill.name}: not in skills.lock.json — run scripts/lock_skills.py"
        if content_hash(skill.name) != locked["sha256"]:
            assert skill.version != locked["version"], (
                f"{skill.name}: prompt or settings changed but version is still {skill.version}"
            )
            raise AssertionError(
                f"{skill.name}: bumped to {skill.version}; run scripts/lock_skills.py"
            )
        assert skill.version == locked["version"]
