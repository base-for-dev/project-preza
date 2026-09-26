"""Task source materials -> one compact `FactSheet`, via the `source-digest` skill.

A task arrives as a pile of material — a repo digest, docs, the team's story
in their own words, constraints like "7 minutes". Outline and content prompts
must stay small to fit the 5-minute generation budget on a slow model, so one
LLM call first boils everything down to a fact sheet (~2-3k characters) that
then *is* the brief for every later stage.
"""

from __future__ import annotations

from inference import InferenceClient, load_skill
from pydantic import BaseModel, Field

# Raw material sent to the digest call. Bigger means a slower call; this keeps
# a free-tier model's digest well inside its 75 s share of the budget.
SOURCE_BUDGET = 20_000
STORY_BUDGET = 8_000


class NamedText(BaseModel):
    name: str
    text: str


class SourceImage(BaseModel):
    """A picture from the talk's material (a product screenshot, a photo)."""

    name: str
    content_type: str
    data_b64: str


class SourceBundle(BaseModel):
    """Everything the user handed over for one talk, already converted to text."""

    id: str
    images: list[SourceImage] = Field(default_factory=list)
    repos: list[NamedText] = Field(default_factory=list)
    documents: list[NamedText] = Field(default_factory=list)
    # How the team arrived at the solution, in their own words — free text.
    story: str = ""

    def source_text(self, budget: int = SOURCE_BUDGET) -> str:
        """All material as one prompt-ready string, story first, trimmed to `budget`.

        The story is the only source written *for* the talk, so it's kept whole
        (up to STORY_BUDGET); the rest shares what's left, docs before repos
        since hand-picked docs are more on-point than a repo's own Markdown.
        """
        parts: list[str] = []
        if self.story.strip():
            parts.append(f"# Team story\n{self.story.strip()[:STORY_BUDGET]}")
        remaining = budget - sum(len(p) for p in parts)
        rest = [*self.documents, *self.repos]
        for i, item in enumerate(rest):
            share = remaining // (len(rest) - i)
            chunk = f"# Source: {item.name}\n{item.text.strip()}"[:share]
            parts.append(chunk)
            remaining -= len(chunk)
        return "\n\n".join(parts)


class FactSheet(BaseModel):
    """What the talk can draw on — every item traceable to the sources."""

    project_name: str = ""
    one_liner: str = ""
    audience: str = ""
    problem: list[str] = Field(default_factory=list)
    solution: list[str] = Field(default_factory=list)
    how_it_works: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    results: list[str] = Field(default_factory=list)
    journey: list[str] = Field(default_factory=list)
    differentiators: list[str] = Field(default_factory=list)
    demo: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)

    def to_text(self) -> str:
        """Render as the brief text later stages read."""
        lines = []
        if self.project_name:
            lines.append(f"Project: {self.project_name}")
        if self.one_liner:
            lines.append(f"In one line: {self.one_liner}")
        if self.audience:
            lines.append(f"Audience: {self.audience}")
        sections = [
            ("Problem", self.problem),
            ("Solution", self.solution),
            ("How it works", self.how_it_works),
            ("Tech stack", self.tech_stack),
            ("Results and numbers", self.results),
            ("How the team got here", self.journey),
            ("Why it's different", self.differentiators),
            ("Demo moments", self.demo),
            ("Next steps", self.next_steps),
        ]
        for title, items in sections:
            if items:
                lines.append(f"\n{title}:")
                lines.extend(f"- {item}" for item in items)
        return "\n".join(lines)


def digest_sources(
    bundle: SourceBundle,
    request: str,
    *,
    client: InferenceClient | None = None,
) -> FactSheet:
    """One LLM call: all source material + the talk request -> a `FactSheet`.

    `request` is what the user asked for ("выступление на финале хакатона, 7
    минут") — it steers which facts matter and sets the output language.
    """
    skill = load_skill("source-digest")
    inference_client = client or InferenceClient()
    user_content = (
        f"Talk request:\n{request.strip() or '(not given)'}\n\n"
        f"Source material:\n{bundle.source_text()}\n\n"
        'Respond with JSON: {"project_name": ..., "one_liner": ..., "audience": ..., '
        '"problem": [...], "solution": [...], "how_it_works": [...], "tech_stack": [...], '
        '"results": [...], "journey": [...], "differentiators": [...], "demo": [...], '
        '"next_steps": [...]}'
    )
    return inference_client.complete_structured(
        model=skill.model,
        system_prompt=skill.prompt,
        user_content=user_content,
        temperature=skill.temperature,
        max_tokens=skill.max_tokens,
        fallback_models=skill.fallback_models,
        timeout=skill.timeout,
        response_model=FactSheet,
    )
