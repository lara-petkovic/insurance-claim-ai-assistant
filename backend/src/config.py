from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PROFILE = "dev"
CONFIG_PROFILES = {"env", "dev", "prod"}


class ConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    openai_text_model: str
    openai_vision_model: str
    openai_require_models: bool
    log_level: str
    log_file: str
    log_to_console: bool


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


def _config_string(data: dict[str, Any], key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"Configuration value '{key}' must be a non-empty string.")
    return value.strip()


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


def _selected_profile() -> str:
    profile = os.getenv("APP_ENV", DEFAULT_CONFIG_PROFILE).strip().lower()
    if profile not in CONFIG_PROFILES:
        allowed_profiles = ", ".join(sorted(CONFIG_PROFILES))
        raise ConfigurationError(f"APP_ENV must be one of: {allowed_profiles}.")
    return profile


def _default_config_file(profile: str) -> Path:
    return BACKEND_DIR / "config" / f"config.{profile}.json"


@lru_cache
def get_settings() -> Settings:
    profile = _selected_profile()
    config_path = Path(os.getenv("APP_CONFIG_FILE", _default_config_file(profile))).expanduser().resolve()
    config = _read_config(config_path)
    model = config.get("model")
    if not isinstance(model, dict):
        raise ConfigurationError("Configuration value 'model' must be a JSON object.")
    logging_config = config.get("logging", {})
    if not isinstance(logging_config, dict):
        raise ConfigurationError("Configuration value 'logging' must be a JSON object.")

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
    log_to_console = logging_config.get("to_console", True)
    if not isinstance(log_to_console, bool):
        raise ConfigurationError("Configuration value 'logging.to_console' must be true or false.")
    log_level = os.getenv("PROJECT_LOG_LEVEL") or _config_string(logging_config, "level", "INFO")
    if log_level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigurationError("Configuration value 'logging.level' must be a valid Python logging level.")

    return Settings(
        openai_api_key=_secret_value("OPENAI_API_KEY"),
        openai_text_model=text_model,
        openai_vision_model=vision_model,
        openai_require_models=_environment_bool("OPENAI_REQUIRE_MODELS", require_models),
        log_level=log_level.upper(),
        log_file=os.getenv("PROJECT_LOG_FILE") or _config_string(logging_config, "file", "logs/claim-checker.log"),
        log_to_console=_environment_bool("PROJECT_LOG_TO_CONSOLE", log_to_console),
    )


__all__ = ["ConfigurationError", "Settings", "get_settings"]
