"""Which language the deck must be written in — decided by code, not the model.

The skills tell the writer to use the brief's language, but a model reliably
drifts into English when everything around the brief is English (the skill
prompts, the template's layout names and sample text, catalogue
descriptions) — seen live: a Russian brief "Презентация про кошек" came back
as an all-English plan. So the language is detected here, stated explicitly
in every prompt, and checked on the answer.
"""

from __future__ import annotations

import re

_CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)
_LATIN = re.compile(r"[a-z]", re.IGNORECASE)

# Share of Cyrillic among letters above which a text counts as Russian.
_RUSSIAN_SHARE = 0.3


def deck_language(text: str) -> str | None:
    """ "Russian" or "English" for a brief, or None when it's too short to tell."""
    cyr = len(_CYRILLIC.findall(text))
    lat = len(_LATIN.findall(text))
    if cyr + lat < 3:
        return None
    return "Russian" if cyr >= _RUSSIAN_SHARE * (cyr + lat) else "English"


def is_in(language: str | None, text: str) -> bool:
    """Whether `text` reads as `language` (empty text and unknown language pass)."""
    if not language or not text.strip():
        return True
    return deck_language(text) in (None, language)


def language_line(language: str | None) -> str:
    """The explicit instruction put into every writing prompt."""
    if not language:
        return ""
    return (
        f"Output language: {language}. Write every piece of text you return in "
        f"{language} — even though layout names, slide descriptions and these "
        "instructions are in English. Keep only proper nouns and code terms as they are."
    )
