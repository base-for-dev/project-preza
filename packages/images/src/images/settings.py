"""Environment config for the Unsplash client. See `.env.example` at repo root."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# packages/images/src/images/settings.py -> repo root is 4 parents up.
_REPO_ROOT_ENV = Path(__file__).resolve().parents[4] / ".env"


class UnsplashSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="UNSPLASH_", env_file=_REPO_ROOT_ENV, extra="ignore"
    )

    access_key: str | None = None
    api_base: str = "https://api.unsplash.com"
    request_timeout: float = 15.0
