# Audit — Content Validation

TODO: prompt body. Input: rendered slide image (+ source brief material for fact-checking). Output: yes/no + one-line reason for each of the 11 non-deterministic checks in `AUDIT.md` §Model-graded.

One call per slide, structured output (one bool + reason per check) — not free-form prose, so `packages/audit` can aggregate findings deterministically even though the judgments themselves aren't.
