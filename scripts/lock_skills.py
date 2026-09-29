"""Record every skill's version and content fingerprint in skills/skills.lock.json.

    uv run python scripts/lock_skills.py

Run it after changing a skill *and* bumping its `version:` in config.yaml. The
test suite fails when a skill's prompt or settings changed but its version did
not, so a behaviour change can never ship under an old version number.
"""

from __future__ import annotations

import json
from pathlib import Path

from inference import content_hash, list_skills

LOCK = Path(__file__).resolve().parents[1] / "skills" / "skills.lock.json"


def main() -> None:
    lock = {s.name: {"version": s.version, "sha256": content_hash(s.name)} for s in list_skills()}
    LOCK.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"locked {len(lock)} skills -> {LOCK}")


if __name__ == "__main__":
    main()
