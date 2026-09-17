"""Environment config for the inference client. See `.env.example` at repo root."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# packages/inference/src/inference/settings.py -> repo root is 4 parents up.
_REPO_ROOT_ENV = Path(__file__).resolve().parents[4] / ".env"


class InferenceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="INFERENCE_", env_file=_REPO_ROOT_ENV, extra="ignore"
    )

    api_base: str = "https://openrouter.ai/api/v1"
    api_key: str | None = None
