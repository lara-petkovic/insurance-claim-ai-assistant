import json
from pathlib import Path
from uuid import uuid4

import pytest

from config import ConfigurationError, get_settings

TEST_TEMP_ROOT = Path(__file__).resolve().parents[2] / ".test_tmp"


def make_test_dir():
    temp_path = TEST_TEMP_ROOT / uuid4().hex
    temp_path.mkdir(parents=True)
    return temp_path


def write_config(test_dir, model):
    config_file = test_dir / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "model": model,
                "logging": {
                    "level": "INFO",
                    "file": "logs/test.log",
                    "to_console": True,
                },
            }
        ),
        encoding="utf-8",
    )
    return config_file


def write_profile_config(test_dir, profile, model):
    config_dir = test_dir / "config"
    config_dir.mkdir()
    config_file = config_dir / f"config.{profile}.json"
    config_file.write_text(
        json.dumps(
            {
                "model": model,
                "logging": {
                    "level": "WARNING",
                    "file": f"logs/{profile}.log",
                    "to_console": False,
                },
            }
        ),
        encoding="utf-8",
    )
    return config_file


def test_settings_load_default_dev_profile(monkeypatch):
    test_dir = make_test_dir()
    write_profile_config(
        test_dir,
        "dev",
        {
            "text_model": "dev-text-model",
            "planning_model": "dev-planning-model",
            "vision_model": "dev-vision-model",
            "require_models": False,
        },
    )
    monkeypatch.chdir(test_dir)
    monkeypatch.setattr("config.BACKEND_DIR", test_dir)
    monkeypatch.delenv("APP_CONFIG_FILE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY_FILE", raising=False)
    monkeypatch.delenv("OPENAI_TEXT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_PLANNING_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_VISION_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_REQUIRE_MODELS", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.openai_text_model == "dev-text-model"
    assert settings.openai_planning_model == "dev-planning-model"
    assert settings.openai_vision_model == "dev-vision-model"
    assert settings.openai_require_models is False
    assert settings.openai_api_key is None
    assert settings.log_level == "WARNING"
    assert settings.log_file == "logs/dev.log"
    assert settings.log_to_console is False


def test_settings_load_selected_prod_profile(monkeypatch):
    test_dir = make_test_dir()
    write_profile_config(
        test_dir,
        "prod",
        {
            "text_model": "prod-text-model",
            "planning_model": "prod-planning-model",
            "vision_model": "prod-vision-model",
            "require_models": True,
        },
    )
    monkeypatch.setattr("config.BACKEND_DIR", test_dir)
    monkeypatch.delenv("APP_CONFIG_FILE", raising=False)
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("OPENAI_TEXT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_PLANNING_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_VISION_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_REQUIRE_MODELS", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.openai_text_model == "prod-text-model"
    assert settings.openai_planning_model == "prod-planning-model"
    assert settings.openai_vision_model == "prod-vision-model"
    assert settings.openai_require_models is True
    assert settings.log_file == "logs/prod.log"


def test_environment_overrides_json(monkeypatch):
    test_dir = make_test_dir()
    config_file = write_config(
        test_dir,
        {
            "text_model": "json-model",
            "require_models": True,
        },
    )
    monkeypatch.setenv("APP_CONFIG_FILE", str(config_file))
    monkeypatch.setenv("APP_ENV", "env")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_TEXT_MODEL", "environment-text-model")
    monkeypatch.setenv("OPENAI_PLANNING_MODEL", "environment-planning-model")
    monkeypatch.setenv("OPENAI_VISION_MODEL", "environment-vision-model")
    monkeypatch.setenv("OPENAI_REQUIRE_MODELS", "false")
    monkeypatch.setenv("PROJECT_LOG_LEVEL", "debug")
    monkeypatch.setenv("PROJECT_LOG_FILE", "logs/environment.log")
    monkeypatch.setenv("PROJECT_LOG_TO_CONSOLE", "false")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.openai_api_key == "test-key"
    assert settings.openai_text_model == "environment-text-model"
    assert settings.openai_planning_model == "environment-planning-model"
    assert settings.openai_vision_model == "environment-vision-model"
    assert settings.openai_require_models is False
    assert settings.log_level == "DEBUG"
    assert settings.log_file == "logs/environment.log"
    assert settings.log_to_console is False


def test_invalid_json_configuration_is_rejected(monkeypatch):
    test_dir = make_test_dir()
    config_file = test_dir / "config.json"
    config_file.write_text("{invalid", encoding="utf-8")
    monkeypatch.setenv("APP_CONFIG_FILE", str(config_file))
    monkeypatch.delenv("APP_ENV", raising=False)
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="invalid JSON"):
        get_settings()


def test_api_key_can_be_loaded_from_secret_file(monkeypatch):
    test_dir = make_test_dir()
    config_file = write_config(
        test_dir,
        {
            "text_model": "json-model",
            "require_models": True,
        },
    )
    secret_file = test_dir / "openai_api_key"
    secret_file.write_text("file-based-test-key\n", encoding="utf-8")
    monkeypatch.setenv("APP_CONFIG_FILE", str(config_file))
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY_FILE", str(secret_file))
    get_settings.cache_clear()

    assert get_settings().openai_api_key == "file-based-test-key"


def test_invalid_app_env_is_rejected(monkeypatch):
    test_dir = make_test_dir()
    write_profile_config(
        test_dir,
        "dev",
        {
            "text_model": "dev-text-model",
            "require_models": False,
        },
    )
    monkeypatch.setattr("config.BACKEND_DIR", test_dir)
    monkeypatch.delenv("APP_CONFIG_FILE", raising=False)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.delenv("OPENAI_PLANNING_MODEL", raising=False)
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="APP_ENV"):
        get_settings()
