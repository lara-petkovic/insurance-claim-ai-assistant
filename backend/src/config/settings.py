from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() not in {"0", "false", "no"}


@dataclass(frozen=True)
class Settings:
    model_provider: str
    openai_api_key: str | None
    openai_text_model: str
    openai_vision_model: str
    openai_require_models: bool


@lru_cache
def get_settings() -> Settings:
    env_file = Path(os.getenv("APP_ENV_FILE", BACKEND_DIR / ".env"))
    load_dotenv(env_file)

    text_model = os.getenv("OPENAI_TEXT_MODEL", "gpt-5.5")
    return Settings(
        model_provider=os.getenv("MODEL_PROVIDER", "openai"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_text_model=text_model,
        openai_vision_model=os.getenv("OPENAI_VISION_MODEL", text_model),
        openai_require_models=_as_bool(os.getenv("OPENAI_REQUIRE_MODELS"), default=True),
    )
