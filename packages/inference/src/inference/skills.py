"""Loader for `skills/<name>/SKILL.md` + `config.yaml`.

One implementation shared by `packages/generator` and `packages/audit` — see
`skills/README.md` for the on-disk convention this reads.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

# Repo layout: packages/inference/src/inference/skills.py -> repo root is 4 parents up.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_SKILLS_DIR = _REPO_ROOT / "skills"


class Skill(BaseModel):
    name: str
    prompt: str
    model: str
    temperature: float
    max_tokens: int
    # Tried in order when `model` fails with a rate limit, provider error or
    # timeout — free-tier pools go down or queue for minutes without notice.
    fallback_models: list[str] = []
    # Per-call read timeout in seconds; None = the client's default. Kept
    # short when fallbacks exist, so a queued model hands over quickly.
    timeout: float | None = None


def load_skill(name: str, *, skills_dir: Path | None = None) -> Skill:
    """Load a skill's system prompt and model config by directory name.

    Raises `FileNotFoundError` if the skill directory, `SKILL.md`, or
    `config.yaml` is missing.
    """
    base = (skills_dir or _SKILLS_DIR) / name
    prompt_path = base / "SKILL.md"
    config_path = base / "config.yaml"

    if not prompt_path.is_file():
        raise FileNotFoundError(f"skill '{name}': no SKILL.md at {prompt_path}")
    if not config_path.is_file():
        raise FileNotFoundError(f"skill '{name}': no config.yaml at {config_path}")

    prompt = prompt_path.read_text(encoding="utf-8")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    for field in ("model", "temperature", "max_tokens"):
        if field not in config:
            raise ValueError(f"skill '{name}': config.yaml missing required field '{field}'")

    return Skill(
        name=name,
        prompt=prompt,
        model=config["model"],
        temperature=config["temperature"],
        max_tokens=config["max_tokens"],
        fallback_models=list(config.get("fallback_models") or []),
        timeout=config.get("timeout"),
    )
