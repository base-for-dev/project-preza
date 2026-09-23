"""Numeric-claim extraction, shared by content generation and the audit."""

from __future__ import annotations

import re

# A figure is "a number with weight": percentages, currency amounts, multipliers
# (x2, 3x), and standalone numbers of 2+ digits. Bare single digits are ignored —
# "3 pillars", "step 2", slide counts — since they are structure, not claims.
_FIGURE_RE = re.compile(
    r"\$\s*\d[\d\s.,]*\d"  # $2.40, $ 1 500
    r"|\d{1,3}(?:[\s ]\d{3})+(?:[.,]\d+)?"  # 12 000, 2 100 (space-grouped thousands)
    r"|\d[\d.,]*\s*%"  # 40%, 40 %, 12,5%
    r"|\b\d{2,}(?:[.,]\d+)?\b"  # 42, 1500, 3.14
    r"|\b\d+\s*[xх×]\b|\b[xх×]\s*\d+\b",  # 2x, x2
    re.IGNORECASE,
)


def figures(text: str) -> set[str]:
    """Normalised numeric figures in `text` (digits only, so '42 %' == '42%')."""
    found = set()
    for match in _FIGURE_RE.findall(text):
        digits = re.sub(r"\D", "", match)
        if digits:
            found.add(digits)
    return found
