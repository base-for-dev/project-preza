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


# Same units _NUMBER_WORDS ends with, but without its negative lookbehind
# (which exists so "10 тысяч" isn't double-counted as two figures when it's
# grounded) — used only to find a unit word stranded right after a bare digit
# that strip_unsupported just removed, e.g. the "тысяч" left behind by
# deleting the "10" in "10 тысяч пользователей".
_UNIT_WORD = re.compile(
    r"тысяч(?:а|и|у|е|ей)?|миллион(?:а|ов|у|е)?|миллиард(?:а|ов|у|е)?", re.IGNORECASE
)
_WS = re.compile(r"\s*")


def strip_unsupported(text: str, allowed: set[str]) -> str:
    """`text` with every figure not in `allowed` cut out.

    For a slot whose *count* of items is structural (a card grid, a table
    row) — dropping the whole bullet the way a free-text slide's corrective
    pass does isn't an option, since that would change how many cards the
    slide has. Removing just the fabricated number and tidying the leftover
    whitespace is the next best thing: the claim is gone, the bullet
    survives. Not grammar-aware — a stray article or preposition can be left
    dangling — but a slightly awkward sentence beats a fabricated statistic.
    """
    spans = [
        m.span() for m in _FIGURE_RE.finditer(text) if re.sub(r"\D", "", m.group(0)) not in allowed
    ]
    spans += [m.span() for m in _NUMBER_WORDS.finditer(text) if m.group(1).lower() not in allowed]
    # Removing a bare digit ("10" out of "10 тысяч") would otherwise strand
    # its unit word — meaningless (and itself still an implied quantity
    # claim) on its own — so sweep it into the same removal.
    extended = []
    for start, end in spans:
        after_ws = end + len(_WS.match(text, end).group())
        unit = _UNIT_WORD.match(text, after_ws)
        extended.append((start, unit.end() if unit else end))
    for start, end in sorted(extended, reverse=True):
        text = text[:start] + text[end:]
    return re.sub(r"\s{2,}", " ", text).strip(" ,.-—")
