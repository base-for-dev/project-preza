"""Talk length -> slide count and per-slide speaking budget.

Plain arithmetic, no LLM: the outline proposes how many seconds each slide
gets, and this module turns a talk length into the numbers around that — how
many slides fit, and how many spoken words a slide's seconds allow.
"""

from __future__ import annotations

# Conversational presenting pace. Russian and English both land around
# 110-130 words per minute when speaking to slides rather than reading.
WORDS_PER_MINUTE = 120

# ~50 seconds per slide is the usual pitch rhythm: enough to make one point,
# short enough that the audience isn't staring at a static slide.
SECONDS_PER_SLIDE = 50
# ТЗ: a deck is 10-15 slides. Only the automatic count is held to it; a slide
# count the user picks explicitly is always respected.
MIN_SLIDES = 10
MAX_SLIDES = 15

# Speaking time assumed per slide when no talk length is given.
DEFAULT_SLIDE_SECONDS = 45


def slide_count_for(duration_minutes: float) -> int:
    count = round(duration_minutes * 60 / SECONDS_PER_SLIDE)
    return max(MIN_SLIDES, min(MAX_SLIDES, count))


def normalize_seconds(proposed: list[int], total_seconds: int) -> list[int]:
    """Scale per-slide seconds so they sum exactly to `total_seconds`.

    Missing/zero proposals get an equal share first; rounding drift goes to
    the longest slide so the total is exact.
    """
    if not proposed:
        return []
    fallback = total_seconds / len(proposed)
    raw = [p if p and p > 0 else fallback for p in proposed]
    scale = total_seconds / sum(raw)
    result = [max(5, round(r * scale)) for r in raw]
    drift = total_seconds - sum(result)
    result[result.index(max(result))] += drift
    return result


def words_for(seconds: int) -> int:
    return max(15, round(seconds * WORDS_PER_MINUTE / 60))
