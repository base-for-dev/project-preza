"""The connection to the model: provider, key and model, set from the app.

Stored by `inference.runtime` in `data/inference.json`; every later call picks
it up at once. The API key is only ever written, never sent back — the app gets
`has_key` and the last four characters.
"""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter
from inference import (
    PRESETS,
    InferenceClient,
    UserConfig,
    effective_settings,
    list_skills,
    load_config,
    save_config,
)
from inference.runtime import DEFAULT_API_BASE, Preset
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/settings")


class ConfigIn(BaseModel):
    provider: str = "openrouter"
    api_base: str = ""
    # None keeps the stored key, "" removes it.
    api_key: str | None = None
    model: str = ""
    vision_model: str = ""
    skill_models: dict[str, str] = Field(default_factory=dict)
    only_my_model: bool = False
    request_timeout: float | None = None

    def merged(self) -> UserConfig:
        stored = load_config()
        key = stored.api_key if self.api_key is None else self.api_key.strip()
        data = self.model_dump(exclude={"api_key"})
        data["skill_models"] = {k: v.strip() for k, v in self.skill_models.items() if v.strip()}
        return UserConfig(**data, api_key=key)


class SkillDefault(BaseModel):
    name: str
    model: str
    modality: str


class ConfigOut(BaseModel):
    provider: str
    api_base: str
    has_key: bool
    key_hint: str
    model: str
    vision_model: str
    skill_models: dict[str, str]
    only_my_model: bool
    request_timeout: float | None
    presets: list[Preset]
    default_api_base: str
    skills: list[SkillDefault]
    # Where the key in use comes from: the app's settings, `.env`, or nowhere.
    key_source: str


def _out(config: UserConfig) -> ConfigOut:
    env_key = effective_settings(UserConfig()).api_key
    key = config.api_key.strip()
    return ConfigOut(
        provider=config.provider,
        api_base=config.api_base,
        has_key=bool(key),
        key_hint=key[-4:] if len(key) >= 8 else "",
        model=config.model,
        vision_model=config.vision_model,
        skill_models=config.skill_models,
        only_my_model=config.only_my_model,
        request_timeout=config.request_timeout,
        presets=PRESETS,
        default_api_base=DEFAULT_API_BASE,
        skills=[
            SkillDefault(name=s.name, model=s.model, modality=s.modality) for s in list_skills()
        ],
        key_source="app" if key else "env" if env_key else "none",
    )


@router.get("")
def get_settings() -> ConfigOut:
    return _out(load_config())


@router.put("")
def put_settings(body: ConfigIn) -> ConfigOut:
    config = body.merged()
    save_config(config)
    return _out(config)


class TestResult(BaseModel):
    ok: bool
    model: str
    seconds: float | None = None
    reply: str = ""
    error: str = ""


@router.post("/test")
def test_connection(body: ConfigIn) -> TestResult:
    """One tiny chat call with the settings as they are on screen (saved or not)."""
    config = body.merged()
    model = config.model.strip() or next(
        (s.model for s in list_skills() if s.modality == "text"), ""
    )
    started = time.monotonic()
    try:
        client = InferenceClient(settings=effective_settings(config))
        reply = client.complete(
            model=model,
            messages=[{"role": "user", "content": "Ответь одним словом: работает?"}],
            temperature=0.0,
            max_tokens=64,
            timeout=30.0,
        )
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:200].replace("\n", " ")
        return TestResult(ok=False, model=model, error=f"{exc.response.status_code}: {detail}")
    except Exception as exc:
        return TestResult(ok=False, model=model, error=str(exc)[:300])
    return TestResult(
        ok=True, model=model, seconds=round(time.monotonic() - started, 1), reply=reply.strip()[:80]
    )


@router.post("/models")
def list_models(body: ConfigIn) -> dict:
    """Model ids the server offers (`GET <address>/models`), for the model picker."""
    settings = effective_settings(body.merged())
    headers = {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
    try:
        res = httpx.get(f"{settings.api_base.rstrip('/')}/models", headers=headers, timeout=15.0)
        res.raise_for_status()
        items = res.json().get("data", [])
    except Exception as exc:
        return {"models": [], "error": str(exc)[:200]}
    return {"models": sorted({m["id"] for m in items if isinstance(m, dict) and "id" in m})}
