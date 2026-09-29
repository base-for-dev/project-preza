"""Environment config for the Unsplash client. See `.env.example` at repo root."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# packages/images/src/images/settings.py -> repo root is 4 parents up.
_ROOT = Path(os.environ.get("PREZA_RESOURCES_DIR") or Path(__file__).resolve().parents[4])
# `.env` in the repo, and in the app's data folder (where the desktop app keeps it).
_ENV_FILES = (_ROOT / ".env", Path(os.environ.get("PREZA_DATA_DIR") or _ROOT / "data") / ".env")


class UnsplashSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UNSPLASH_", env_file=_ENV_FILES, extra="ignore")

    access_key: str | None = None
    api_base: str = "https://api.unsplash.com"
    request_timeout: float = 15.0
