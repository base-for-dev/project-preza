"""The one result type every check produces."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Finding(BaseModel):
    check: str
    # "model" findings (content_validation.py) are best-effort, run on
    # request — see AUDIT.md's §Модельные.
    kind: Literal["deterministic", "model"] = "deterministic"
    slide_index: int
    shape_id: int | None = None  # None for slide-level findings
    # The second shape a finding is about (the other one of an overlapping pair).
    related_shape_id: int | None = None
    message: str
