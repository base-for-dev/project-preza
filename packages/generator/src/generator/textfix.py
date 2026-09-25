"""Surgical rewrite of individual strings that broke a hard rule.

Whole-slide rewrites keep the offending number or length because the writer
"needs" it; rewriting only the flagged strings, each with its own rule, is far
more reliable. Prompt lives in `skills/text-fix`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from inference import InferenceClient, load_skill
from pydantic import BaseModel, Field


class Rewrites(BaseModel):
    items: list[str] = Field(default_factory=list)


@dataclass
class Fix:
    """One string to repair, with the rules it broke."""

    text: str
    forbidden_figures: list[str] = field(default_factory=list)
    max_chars: int | None = None
    max_words: int | None = None

    def rules(self) -> str:
        parts = []
        if self.forbidden_figures:
            parts.append(f"no figures: {', '.join(self.forbidden_figures)}")
        if self.max_chars is not None:
            parts.append(f"max {self.max_chars} chars")
        if self.max_words is not None:
            parts.append(f"max {self.max_words} words")
        return "; ".join(parts)


def rewrite_strings(fixes: list[Fix], client: InferenceClient) -> list[str]:
    """New text for each fix, same order; a failed call returns the originals."""
    if not fixes:
        return []
    skill = load_skill("text-fix")
    listing = "\n".join(f"{i}. [{fix.rules()}] {fix.text}" for i, fix in enumerate(fixes, start=1))
    try:
        result = client.complete_structured(
            model=skill.model,
            system_prompt=skill.prompt,
            user_content=f"Strings to fix:\n{listing}",
            temperature=skill.temperature,
            max_tokens=skill.max_tokens,
            fallback_models=skill.fallback_models,
            timeout=skill.timeout,
            response_model=Rewrites,
        )
    except Exception:
        return [fix.text for fix in fixes]
    if len(result.items) != len(fixes):
        return [fix.text for fix in fixes]
    return [new.strip() or fix.text for new, fix in zip(result.items, fixes, strict=True)]
