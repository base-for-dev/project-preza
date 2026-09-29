"""Environment config for the inference client. See `.env.example` at repo root."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# packages/inference/src/inference/settings.py -> repo root is 4 parents up.
_ROOT = Path(os.environ.get("PREZA_RESOURCES_DIR") or Path(__file__).resolve().parents[4])
# `.env` in the repo, and in the app's data folder (where the desktop app keeps it).
_ENV_FILES = (_ROOT / ".env", Path(os.environ.get("PREZA_DATA_DIR") or _ROOT / "data") / ".env")


class InferenceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INFERENCE_", env_file=_ENV_FILES, extra="ignore")

    api_base: str = "https://openrouter.ai/api/v1"
    api_key: str | None = None
    # Read timeout per LLM call, seconds. Open-weight models on shared/free
    # provider pools generate a full 10-slide outline slowly and with high
    # variance (seen anywhere from ~40s to over 160s for the same request),
    # so the default is generous — better to wait than to fail a generation
    # that was seconds from finishing. Override via INFERENCE_REQUEST_TIMEOUT.
    request_timeout: float = 270.0
    # Extra attempts after the first on a *transient* transport failure
    # (dropped connection, SSL EOF mid-stream) — not on timeouts or HTTP
    # errors, which aren't helped by an immediate retry. 0 disables retries.
    max_retries: int = 1
