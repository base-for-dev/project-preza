# preza-audit

Детерминированные и модельные проверки IR сгенерированной колоды.

## Interface

```python
from audit import Finding, run_checks

findings: list[Finding] = run_checks(deck, template_deck)
```

- `deck` — a composed `Deck` (output of `layout.compose_deck`).
- `template_deck` — the original parsed `Deck` for that template. Used to
  derive the "allowed" palette/fonts/sizes via `design_system.extract_colors`/
  `extract_typography` — called on `template_deck`, not `deck`, since the
  template defines what's in-scope.

```python
class Finding(BaseModel):
    check: str  # stable id, e.g. "shape_out_of_bounds"
    kind: Literal["deterministic", "model"] = "deterministic"
    slide_index: int
    shape_id: int | None = None  # None for slide-level findings
    message: str
```

## Checks implemented (see `checks.py` for exact thresholds/comments)

Bounds/layout: `shape_out_of_bounds`, `shapes_overlap` (>5% of the smaller
shape's area), `text_overflow` (heuristic: `1.2 * font_size_pt` per
paragraph line vs actual shape height).

Template compliance (against `template_deck`'s own extracted tokens):
`font_not_in_template`, `size_not_in_scale` (±0.5pt tolerance),
`color_not_in_palette` (rgb colors only — theme colors are trivially
compliant).

Density (independent re-verification of what `layout`'s variant logic is
supposed to already respect): `too_many_bullets` (>6 non-empty paragraphs
in the body-ish shape), `bullet_too_long` (>15 words in one paragraph),
`table_too_large` (>7 rows or >5 cols), `slide_fill_ratio` (sum of shape
bbox areas / slide area, outside 25%-75% — an approximation, overlapping
shapes double-count).

Integrity: `placeholder_text_left` (case-insensitive "lorem ipsum", "xxx",
"todo", "вставьте текст"), `empty_or_title_only_slide`, `duplicate_slide`
(identical title + identical set of body/bullet paragraph texts — second
occurrence flagged, referencing the first slide's index), `unsupported_figure`
(a number on the slide the source brief never mentions — only when
`run_checks` is given `source_text`), `language_drift` (slide text that
doesn't read as the brief's own language — via `generator.language`, only
when `source_text` is given).

## Model-graded checks (`content_validation.py`)

```python
from audit import run_model_checks

findings: list[Finding] = run_model_checks(deck, brief, slide_images)
```

`slide_images` maps a slide's `index` to a `data:` URI of its rendered
image — this package never renders anything itself (see `export.render`).
One VLM call per slide (`skills/audit-content-validation`), ten checks from
AUDIT.md's §Модельные, each surfaced as a `kind="model"` `Finding` when it
fails. Best-effort throughout: a slide missing from `slide_images`, or a
judgment call that raises, is silently skipped rather than failing the
whole pass — see `judge_slide`, which never raises.

Deliberately separate from `run_checks`: an LLM call per slide is slow and
costs money on every call, so it never runs inside the free, instant,
always-on deterministic pass — only when a caller asks for it.

## Checks explicitly NOT implemented (deferred, not forgotten)

Each of these needs a pipeline capability that doesn't exist yet:

- **alignment-to-layout-guides** — no guide data in the IR.
- **margin/safe-zone** — no margin data in the IR.
- **picture aspect distortion** — `layout` never touches `Picture` shapes,
  so this can't regress in generated content; not applicable pre-export.
- **logo/footer position** — no logo concept in the IR.
- **text-contrast 4.5:1** — no resolved slide background color available.
- **chart series count / chart axis-legend labels** — no chart shape
  modeled in `ir_schema`; charts become `PassthroughShape`.
- **file-doesn't-open / slide-flattened-to-image** — both are `export`-stage
  concerns; nothing to check pre-export.

## Server

`POST /api/audit` runs parse → design_system → outline → content → layout
(3 variants) → `run_checks` per variant against the parsed template deck —
part of the 5-minute generation budget.

`POST /api/audit/deep` is separate and on-demand: renders the deck (needs
LibreOffice — 501 if it's not installed) and calls `run_model_checks`. Not
part of generation or its budget.

See `ARCHITECTURE.md` in the repo root for how this package fits the pipeline.
