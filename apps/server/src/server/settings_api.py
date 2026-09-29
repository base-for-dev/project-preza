"""The connection to the model: provider, key and model, set from the app.

Stored by `inference.runtime` in `data/inference.json`; every later call picks
it up at once. The API key is only ever written, never sent back — the app gets
`has_key` and the last four characters.
"""

from __future__ import annotations

import re
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
from pydantic import BaseModel, Field, field_validator

from server import object_store

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

    @field_validator("api_base")
    @classmethod
    def _http_only(cls, value: str) -> str:
        value = value.strip()
        if value and not re.match(r"^https?://[^\s/]+", value):
            raise ValueError("the address must start with http:// or https://")
        return value

    def merged(self, *, probe: bool = False) -> UserConfig:
        """The config this request describes. With `probe` (test / model list) the
        stored key is only reused for the address it was saved for, so a request
        can't make the server hand it to some other host."""
        stored = load_config()
        key = stored.api_key if self.api_key is None else self.api_key.strip()
        data = self.model_dump(exclude={"api_key"})
        data["skill_models"] = {k: v.strip() for k, v in self.skill_models.items() if v.strip()}
        config = UserConfig(**data, api_key=key)
        if probe and self.api_key is None and config.base().rstrip("/") != stored.base().rstrip("/"):
            config = config.model_copy(update={"api_key": ""})
        return config


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


def _probe_settings(config: UserConfig):
    """Settings for a probe: the environment's key is never sent to an address the user typed."""
    settings = effective_settings(config)
    stored = effective_settings(load_config())
    if not config.api_key.strip() and settings.api_base.rstrip("/") != stored.api_base.rstrip("/"):
        settings = settings.model_copy(update={"api_key": ""})
    return settings


@router.post("/test")
def test_connection(body: ConfigIn) -> TestResult:
    """One tiny chat call with the settings as they are on screen (saved or not)."""
    config = body.merged(probe=True)
    model = config.model.strip() or next(
        (s.model for s in list_skills() if s.modality == "text"), ""
    )
    started = time.monotonic()
    try:
        client = InferenceClient(settings=_probe_settings(config))
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
    settings = _probe_settings(body.merged(probe=True))
    headers = {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
    try:
        res = httpx.get(f"{settings.api_base.rstrip('/')}/models", headers=headers, timeout=15.0)
        res.raise_for_status()
        items = res.json().get("data", [])
    except Exception as exc:
        return {"models": [], "error": str(exc)[:200]}
    return {"models": sorted({m["id"] for m in items if isinstance(m, dict) and "id" in m})}


# --- S3 storage ---------------------------------------------------------------


class StorageIn(BaseModel):
    endpoint_url: str = ""
    region: str = ""
    bucket: str = ""
    access_key: str = ""
    # None keeps the stored secret, "" removes it.
    secret_key: str | None = None
    prefix: str = "preza/"
    path_style: bool = False

    def merged(self) -> object_store.StorageConfig:
        stored = object_store.load_config()
        secret = stored.secret_key if self.secret_key is None else self.secret_key.strip()
        data = self.model_dump(exclude={"secret_key"})
        return object_store.StorageConfig(**data, secret_key=secret)


class StorageOut(BaseModel):
    connected: bool
    endpoint_url: str
    region: str
    bucket: str
    access_key: str
    has_secret: bool
    prefix: str
    path_style: bool


def _storage_out(config: object_store.StorageConfig) -> StorageOut:
    return StorageOut(
        connected=config.connected(),
        endpoint_url=config.endpoint_url,
        region=config.region,
        bucket=config.bucket,
        access_key=config.access_key,
        has_secret=bool(config.secret_key),
        prefix=config.prefix,
        path_style=config.path_style,
    )


@router.get("/storage")
def get_storage() -> StorageOut:
    return _storage_out(object_store.load_config())


@router.put("/storage")
def put_storage(body: StorageIn) -> StorageOut:
    config = body.merged()
    object_store.save_config(config)
    return _storage_out(config)


class StorageTest(BaseModel):
    ok: bool
    error: str = ""


@router.post("/storage/test")
def test_storage(body: StorageIn) -> StorageTest:
    """Reach the bucket and write, then delete, a probe object — with the form as it is."""
    config = body.merged()
    if not config.connected():
        return StorageTest(ok=False, error="Нужны бакет, ключ доступа и секретный ключ")
    try:
        object_store.ObjectStore(config).check()
    except Exception as exc:
        return StorageTest(ok=False, error=str(exc)[:300])
    return StorageTest(ok=True)
