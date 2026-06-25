from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_FILE = BACKEND_DIR / "config.json"


class ConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    model_provider: str
    openai_api_key: str | None
    openai_text_model: str
    openai_vision_model: str
    openai_require_models: bool


def _read_config(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as config_file:
            data = json.load(config_file)
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Configuration file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Configuration file contains invalid JSON: {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigurationError(f"Configuration file must contain a JSON object: {path}")
    return data


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"Configuration value '{key}' must be a non-empty string.")
    return value.strip()


def _environment_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _secret_value(name: str) -> str | None:
    direct_value = os.getenv(name)
    if direct_value:
        return direct_value

    secret_file = os.getenv(f"{name}_FILE")
    if not secret_file:
        return None
    try:
        value = Path(secret_file).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ConfigurationError(f"Could not read secret file for {name}: {secret_file}") from exc
    return value or None


@lru_cache
def get_settings() -> Settings:
    config_path = Path(os.getenv("APP_CONFIG_FILE", DEFAULT_CONFIG_FILE)).expanduser().resolve()
    config = _read_config(config_path)
    model = config.get("model")
    if not isinstance(model, dict):
        raise ConfigurationError("Configuration value 'model' must be a JSON object.")

    text_model = os.getenv("OPENAI_TEXT_MODEL") or _required_string(model, "text_model")
    configured_vision_model = model.get("vision_model")
    vision_model = os.getenv("OPENAI_VISION_MODEL") or (
        configured_vision_model.strip()
        if isinstance(configured_vision_model, str) and configured_vision_model.strip()
        else text_model
    )
    require_models = model.get("require_models", True)
    if not isinstance(require_models, bool):
        raise ConfigurationError("Configuration value 'model.require_models' must be true or false.")

    return Settings(
        model_provider=os.getenv("MODEL_PROVIDER") or _required_string(model, "provider"),
        openai_api_key=_secret_value("OPENAI_API_KEY"),
        openai_text_model=text_model,
        openai_vision_model=vision_model,
        openai_require_models=_environment_bool("OPENAI_REQUIRE_MODELS", require_models),
    )


__all__ = ["ConfigurationError", "Settings", "get_settings"]
