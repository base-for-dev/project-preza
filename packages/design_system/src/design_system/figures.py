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


# Precise quantities a writer can smuggle in as words to dodge a digit check
# ("Пятьдесят тысяч бронирований", "в десять раз"). Vague words ("десятки",
# "сотни", "несколько") are deliberately not here. Stem-matched, so case
# endings do not matter.
_NUMBER_WORDS = re.compile(
    r"\b(десят(?:ь|и|ью)|двадцат(?:ь|и|ью)|тридцат(?:ь|и|ью)|сорок(?:а)?|"
    r"пятьдесят|пятидесяти|шестьдесят|шестидесяти|семьдесят|семидесяти|"
    r"восемьдесят|восьмидесяти|девяносто|девяноста|сто|двести|двухсот|триста|"
    r"трёхсот|четыреста|пятьсот|шестьсот|семьсот|восемьсот|девятьсот|"
    r"(?<!\d )(?<!\d)тысяч(?:а|и|у|е|ей)?|"
    r"(?<!\d )(?<!\d)миллион(?:а|ов|у|е)?|(?<!\d )(?<!\d)миллиард(?:а|ов|у|е)?)\b",
    re.IGNORECASE,
)


def figures(text: str) -> set[str]:
    """Normalised numeric figures in `text`.

    Digits only, so '42 %' == '42%'; spelled-out precise quantities are kept as
    their lower-cased stem word ("пятьдесят") so a number written in words is
    checked against the brief exactly like one written in digits.
    """
    found = set()
    for match in _FIGURE_RE.findall(text):
        digits = re.sub(r"\D", "", match)
        if digits:
            found.add(digits)
    for match in _NUMBER_WORDS.finditer(text):
        found.add(match.group(1).lower())
    return found
