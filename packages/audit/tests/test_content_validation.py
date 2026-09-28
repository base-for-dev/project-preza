"""Model-graded checks: verdict -> Finding mapping and failure handling.

uv run pytest packages/audit
"""

from __future__ import annotations

import threading

from audit.content_validation import CheckResult, SlideVerdict, judge_slide, run_model_checks
from ir_schema import Deck, Paragraph, Slide, TextBoxShape, TextRun

SLIDE_WIDTH = 9_144_000
SLIDE_HEIGHT = 6_858_000


def _ok(reason: str = "") -> CheckResult:
    return CheckResult(ok=True, reason=reason)


def _fail(reason: str) -> CheckResult:
    return CheckResult(ok=False, reason=reason)


def _all_ok_verdict(**overrides: CheckResult) -> SlideVerdict:
    fields = {
        "title_is_conclusion": _ok(),
        "content_matches_title": _ok(),
        "single_point": _ok(),
        "facts_traceable": _ok(),
        "has_real_content": _ok(),
        "images_on_topic": _ok(),
        "no_leftover_junk": _ok(),
        "no_typos": _ok(),
        "table_rows_on_point": _ok(),
        "connects_to_neighbors": _ok(),
    }
    fields.update(overrides)
    return SlideVerdict(**fields)


class _Client:
    def __init__(self, verdicts: list[SlideVerdict | Exception]):
        self.verdicts = verdicts
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def complete_structured(self, **kwargs):
        with self._lock:
            self.calls.append(kwargs)
            result = self.verdicts[len(self.calls) - 1]
        if isinstance(result, Exception):
            raise result
        return result


def _title_shape(shape_id: int, text: str) -> TextBoxShape:
    return TextBoxShape(
        shape_id=shape_id,
        name=f"t{shape_id}",
        z_order=0,
        left=0,
        top=0,
        width=SLIDE_WIDTH,
        height=1_000_000,
        is_placeholder=True,
        placeholder_type="TITLE (1)",
        paragraphs=[Paragraph(runs=[TextRun(text=text)])],
    )


def _deck(titles: list[str]) -> Deck:
    slides = [
        Slide(index=i, layout_name="L", shapes=[_title_shape(i, t)]) for i, t in enumerate(titles)
    ]
    return Deck(slide_width=SLIDE_WIDTH, slide_height=SLIDE_HEIGHT, slides=slides)


def test_a_failed_check_becomes_a_model_finding():
    deck = _deck(["Заголовок"])
    verdict = _all_ok_verdict(no_typos=_fail("опечатка в слове 'презинтация'"))
    client = _Client([verdict])

    findings = run_model_checks(deck, "бриф", {0: "data:image/png;base64,x"}, client=client)  # type: ignore[arg-type]

    assert len(findings) == 1
    assert findings[0].check == "typo"
    assert findings[0].kind == "model"
    assert findings[0].slide_index == 0
    assert "опечатка" in findings[0].message


def test_all_ok_verdict_produces_no_findings():
    deck = _deck(["Заголовок"])
    client = _Client([_all_ok_verdict()])
    findings = run_model_checks(deck, "бриф", {0: "data:image/png;base64,x"}, client=client)  # type: ignore[arg-type]
    assert findings == []


def test_slide_without_an_image_is_skipped_without_a_call():
    deck = _deck(["A", "B"])
    client = _Client([_all_ok_verdict()])
    findings = run_model_checks(deck, "бриф", {1: "data:image/png;base64,x"}, client=client)  # type: ignore[arg-type]
    assert len(client.calls) == 1
    assert findings == []


def test_failed_judgment_call_is_skipped_not_raised():
    deck = _deck(["A"])
    client = _Client([RuntimeError("boom")])
    findings = run_model_checks(deck, "бриф", {0: "data:image/png;base64,x"}, client=client)  # type: ignore[arg-type]
    assert findings == []


def test_neighbor_titles_are_passed_for_the_connectivity_check():
    deck = _deck(["Первый", "Второй", "Третий"])
    client = _Client([_all_ok_verdict(), _all_ok_verdict(), _all_ok_verdict()])
    images = {0: "data:x", 1: "data:x", 2: "data:x"}

    run_model_checks(deck, "бриф", images, client=client)  # type: ignore[arg-type]

    # Calls run concurrently, so find the one for the middle slide by its own
    # title rather than assuming call order.
    middle_prompt = next(
        str(c["user_content"])
        for c in client.calls
        if "Slide title (as generated): Второй" in str(c["user_content"])
    )
    assert "Первый" in middle_prompt
    assert "Третий" in middle_prompt


def test_judge_slide_returns_none_on_failure_without_raising():
    client = _Client([RuntimeError("boom")])
    result = judge_slide(
        "data:x",
        title="T",
        brief="бриф",
        prev_title=None,
        next_title=None,
        client=client,  # type: ignore[arg-type]
    )
    assert result is None
