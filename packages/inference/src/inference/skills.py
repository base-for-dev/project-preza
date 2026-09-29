"""Loader for `skills/<name>/SKILL.md` + `config.yaml`.

One implementation shared by `packages/generator` and `packages/audit` — see
`skills/README.md` for the on-disk convention this reads.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml
from pydantic import BaseModel

# Repo layout: packages/inference/src/inference/skills.py -> repo root is 4 parents up.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_SKILLS_DIR = _REPO_ROOT / "skills"


_SEMVER = re.compile(r"\d+\.\d+\.\d+")


class Skill(BaseModel):
    name: str
    # Semantic version from config.yaml. Behaviour changes -> bump it; the lock
    # file (skills/skills.lock.json) and its test enforce that.
    version: str
    prompt: str
    # "vision": judges pictures, so it needs a vision-capable model of its own.
    modality: str = "text"
    model: str
    temperature: float
    max_tokens: int
    # Tried in order when `model` fails with a rate limit, provider error or
    # timeout — free-tier pools go down or queue for minutes without notice.
    fallback_models: list[str] = []
    # Per-call read timeout in seconds; None = the client's default. Kept
    # short when fallbacks exist, so a queued model hands over quickly.
    timeout: float | None = None


def load_skill(name: str, *, skills_dir: Path | None = None, user_config: bool = True) -> Skill:
    """Load a skill's system prompt and model config by directory name.

    The model the user chose in the settings screen replaces the skill's own
    (see `inference.runtime`) — only for the repo's skills, and never when
    `user_config` is False (listing versions shows the files as they are).

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

    for field in ("version", "model", "temperature", "max_tokens"):
        if field not in config:
            raise ValueError(f"skill '{name}': config.yaml missing required field '{field}'")

    if not _SEMVER.fullmatch(str(config["version"])):
        raise ValueError(f"skill '{name}': version {config['version']!r} is not MAJOR.MINOR.PATCH")

    skill = Skill(
        name=name,
        version=str(config["version"]),
        prompt=prompt,
        modality=config.get("modality", "text"),
        model=config["model"],
        temperature=config["temperature"],
        max_tokens=config["max_tokens"],
        fallback_models=list(config.get("fallback_models") or []),
        timeout=config.get("timeout"),
    )
    if user_config and skills_dir is None:
        from inference.runtime import apply_to_skill  # runtime imports this module

        skill = apply_to_skill(skill)
    return skill


def list_skills(*, skills_dir: Path | None = None) -> list[Skill]:
    """Every skill on disk, by name."""
    base = skills_dir or _SKILLS_DIR
    return [
        load_skill(p.name, skills_dir=base, user_config=False)
        for p in sorted(base.iterdir())
        if (p / "SKILL.md").is_file()
    ]


def content_hash(name: str, *, skills_dir: Path | None = None) -> str:
    """Fingerprint of a skill's prompt and settings, ignoring its own version line.

    What the lock file records: if this changes while `version` does not, the
    skill's behaviour changed without a version bump.
    """
    base = (skills_dir or _SKILLS_DIR) / name
    config = re.sub(r"(?m)^version:.*\n", "", (base / "config.yaml").read_text(encoding="utf-8"))
    digest = hashlib.sha256()
    digest.update((base / "SKILL.md").read_bytes())
    digest.update(config.encode("utf-8"))
    return digest.hexdigest()
