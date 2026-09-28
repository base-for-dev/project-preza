"""Model-graded checks on a rendered slide image — AUDIT.md's §Модельные.

Ten checks, one VLM call per slide, structured output (a bool + a one-line
reason per check) so the judgments aggregate into `Finding`s the same
deterministic way `checks.py`'s do, even though the judgments themselves
aren't deterministic. (AUDIT.md used to list eleven; "the whole deck is one
language" turned out to need no model call at all — see
`checks._check_deck_language` — so it moved to the deterministic pass.)

Deliberately not part of `run_checks`: an LLM call per slide is slow and
costs money on every single generation, which the free, instant,
always-on deterministic pass must never depend on. This runs only when a
caller asks for it (see apps/server's `POST /api/audit/deep`), against
slide images it doesn't know how to produce itself — rendering is the
caller's job (see `export.render`), this module only judges images it's
handed.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from design_system import is_title
from inference import InferenceClient, image_content, load_skill, text_content
from ir_schema import AutoShape, Deck, Slide, TextBoxShape
from pydantic import BaseModel

from audit.checks import Finding


class CheckResult(BaseModel):
    ok: bool
    reason: str = ""


class SlideVerdict(BaseModel):
    title_is_conclusion: CheckResult
    content_matches_title: CheckResult
    single_point: CheckResult
    facts_traceable: CheckResult
    has_real_content: CheckResult
    images_on_topic: CheckResult
    no_leftover_junk: CheckResult
    no_typos: CheckResult
    table_rows_on_point: CheckResult
    connects_to_neighbors: CheckResult


# (SlideVerdict field, Finding.check id, message used when the model gives no reason)
_CHECKS: list[tuple[str, str, str]] = [
    (
        "title_is_conclusion",
        "title_not_a_conclusion",
        "title names a topic instead of stating a conclusion",
    ),
    ("content_matches_title", "content_off_title", "slide content doesn't support its own title"),
    ("single_point", "no_single_point", "slide doesn't reduce to one coherent point"),
    (
        "facts_traceable",
        "untraceable_fact",
        "a fact or figure isn't grounded in the source material",
    ),
    ("has_real_content", "title_only_content", "slide has no real content beyond its title"),
    ("images_on_topic", "image_off_topic", "an image or icon doesn't relate to the slide's topic"),
    (
        "no_leftover_junk",
        "leftover_junk",
        "leftover scaffolding text (speaker aside, prompt fragment)",
    ),
    ("no_typos", "typo", "a typo on the slide"),
    (
        "table_rows_on_point",
        "table_row_off_point",
        "a table row or legend item doesn't serve the slide's point",
    ),
    (
        "connects_to_neighbors",
        "disconnected_slide",
        "slide doesn't connect logically to its neighbours",
    ),
]


def _slide_title(slide: Slide) -> str:
    for shape in slide.shapes:
        if isinstance(shape, (TextBoxShape, AutoShape)) and is_title(shape):
            return " ".join(run.text for p in shape.paragraphs for run in p.runs).strip()
    return ""


def judge_slide(
    image_data_uri: str,
    *,
    title: str,
    brief: str,
    prev_title: str | None,
    next_title: str | None,
    client: InferenceClient,
) -> SlideVerdict | None:
    """One slide's verdict on all ten checks, or `None` if the call failed.

    Never raises — a judgment call failing (rate limit, malformed reply) is a
    missing opinion, not a pipeline error; the caller just gets no findings
    for that slide instead of the whole deep-audit request failing.
    """
    skill = load_skill("audit-content-validation")
    context = "\n\n".join(
        [
            f"Slide title (as generated): {title or '(no title text found)'}",
            f"Previous slide's title: {prev_title or '(this is the first slide)'}",
            f"Next slide's title: {next_title or '(this is the last slide)'}",
            f"Source brief / material the deck was built from:\n{brief[:4000]}",
        ]
    )
    try:
        return client.complete_structured(
            model=skill.model,
            system_prompt=skill.prompt,
            user_content=[text_content(context), image_content(image_data_uri)],
            temperature=skill.temperature,
            max_tokens=skill.max_tokens,
            fallback_models=skill.fallback_models,
            timeout=skill.timeout,
            response_model=SlideVerdict,
        )
    except Exception:
        return None


def run_model_checks(
    deck: Deck,
    brief: str,
    slide_images: dict[int, str],
    *,
    client: InferenceClient | None = None,
) -> list[Finding]:
    """`Finding`s (kind="model") for every check a judged slide failed.

    `slide_images` maps a slide's `index` to a `data:` URI of its rendered
    image; a slide missing from it (the renderer skipped or failed on it) is
    silently skipped, same as a failed judgment call — best-effort throughout.
    """
    inference_client = client or InferenceClient()
    titles = {slide.index: _slide_title(slide) for slide in deck.slides}
    # (slide, image, previous title, next title) for every slide with an
    # image, keeping each slide's real neighbours from the full deck order.
    judged = [
        (
            slide,
            slide_images[slide.index],
            titles[deck.slides[pos - 1].index] if pos > 0 else None,
            titles[deck.slides[pos + 1].index] if pos < len(deck.slides) - 1 else None,
        )
        for pos, slide in enumerate(deck.slides)
        if slide.index in slide_images
    ]
    if not judged:
        return []

    def judge(i: int) -> SlideVerdict | None:
        slide, image, prev_title, next_title = judged[i]
        return judge_slide(
            image,
            title=titles[slide.index],
            brief=brief,
            prev_title=prev_title,
            next_title=next_title,
            client=inference_client,
        )

    with ThreadPoolExecutor(max_workers=min(6, len(judged))) as pool:
        verdicts = list(pool.map(judge, range(len(judged))))

    findings: list[Finding] = []
    for (slide, *_rest), verdict in zip(judged, verdicts, strict=True):
        if verdict is None:
            continue
        for field, check_id, default_message in _CHECKS:
            result: CheckResult = getattr(verdict, field)
            if not result.ok:
                findings.append(
                    Finding(
                        check=check_id,
                        kind="model",
                        slide_index=slide.index,
                        shape_id=None,
                        message=result.reason or default_message,
                    )
                )
    return findings
