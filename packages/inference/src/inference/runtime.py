"""The connection the user set up in the app, layered over `.env` and the skill files.

`.env` and `skills/*/config.yaml` are the defaults a fresh clone runs with. The
settings screen writes `data/inference.json`, and everything here is read from
it on every call, so a change takes effect without restarting the server:

- provider, address, key and timeout replace the `.env` values;
- a chosen model replaces every text skill's model (and a vision model the
  picture-judging skill's); a model named for one skill wins over both;
- unless "only my model" is off, the skill's own model chain stays behind the
  chosen one as fallbacks — but only on the default provider, where those model
  names exist. On any other server the chosen model is the only one tried.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field

from inference.settings import InferenceSettings
from inference.skills import Skill

# packages/inference/src/inference/runtime.py -> repo root is 4 parents up.
_DEFAULT_PATH = Path(__file__).resolve().parents[4] / "data" / "inference.json"

# The provider whose model names the skill files use.
DEFAULT_API_BASE = InferenceSettings.model_fields["api_base"].default


class Preset(BaseModel):
    id: str
    label: str
    api_base: str
    needs_key: bool = True
    hint: str = ""


PRESETS = [
    Preset(
        id="openrouter",
        label="OpenRouter",
        api_base=DEFAULT_API_BASE,
        hint="Один ключ на много открытых моделей. Ключ: openrouter.ai/keys",
    ),
    Preset(
        id="vk",
        label="Инференс VK (топ-10)",
        api_base="",
        hint="Адрес и ключ выдают организаторы; модель — Qwen 3.8 27B.",
    ),
    Preset(
        id="ollama",
        label="Ollama (локально)",
        api_base="http://localhost:11434/v1",
        needs_key=False,
        hint="Модель уже скачана: `ollama pull qwen3:30b`. Ключ не нужен.",
    ),
    Preset(
        id="lmstudio",
        label="LM Studio (локально)",
        api_base="http://localhost:1234/v1",
        needs_key=False,
        hint="Запустите локальный сервер во вкладке Developer. Ключ не нужен.",
    ),
    Preset(
        id="custom",
        label="Свой сервер (OpenAI-совместимый)",
        api_base="",
        hint="vLLM, llama.cpp, TGI, любой прокси с /chat/completions.",
    ),
]


class UserConfig(BaseModel):
    provider: str = "openrouter"
    api_base: str = ""  # empty: the preset's address, else `.env`
    api_key: str = ""  # empty: `.env`
    model: str = ""  # empty: each skill's own
    vision_model: str = ""  # empty: the vision skill's own
    skill_models: dict[str, str] = Field(default_factory=dict)
    only_my_model: bool = False
    request_timeout: float | None = None

    def base(self) -> str:
        if self.api_base.strip():
            return self.api_base.strip().rstrip("/")
        preset = next((p for p in PRESETS if p.id == self.provider), None)
        return preset.api_base if preset and preset.api_base else ""


def config_path() -> Path:
    return Path(os.environ.get("PREZA_INFERENCE_CONFIG") or _DEFAULT_PATH)


def load_config() -> UserConfig:
    path = config_path()
    if not path.is_file():
        return UserConfig()
    try:
        return UserConfig.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return UserConfig()  # a damaged file must not take generation down


def save_config(config: UserConfig) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    path.chmod(0o600)  # holds an API key


def effective_settings(config: UserConfig | None = None) -> InferenceSettings:
    """`.env` settings with the user's connection laid over them."""
    config = config or load_config()
    settings = InferenceSettings()
    update: dict[str, object] = {}
    if config.base():
        update["api_base"] = config.base()
    if config.api_key.strip():
        update["api_key"] = config.api_key.strip()
    if config.request_timeout:
        update["request_timeout"] = config.request_timeout
    return settings.model_copy(update=update)


def apply_to_skill(skill: Skill, config: UserConfig | None = None) -> Skill:
    """`skill` pointed at the user's model, if they chose one."""
    config = config or load_config()
    if skill.name in config.skill_models and config.skill_models[skill.name].strip():
        chosen = config.skill_models[skill.name].strip()
    elif skill.modality == "vision":
        chosen = config.vision_model.strip()
    else:
        chosen = config.model.strip()
    if not chosen:
        return skill
    own_provider = effective_settings(config).api_base.rstrip("/") == DEFAULT_API_BASE.rstrip("/")
    keep_chain = own_provider and not config.only_my_model and skill.modality != "vision"
    fallbacks = (
        [m for m in [skill.model, *skill.fallback_models] if m != chosen] if keep_chain else []
    )
    return skill.model_copy(update={"model": chosen, "fallback_models": fallbacks})
