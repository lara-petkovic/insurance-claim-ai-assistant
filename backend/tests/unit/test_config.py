import json

import pytest

from config import ConfigurationError, get_settings


def write_config(tmp_path, model):
    config_file = tmp_path / "config.json"
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


def write_profile_config(tmp_path, profile, model):
    config_dir = tmp_path / "config"
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


def test_settings_load_default_dev_profile(monkeypatch, tmp_path):
    write_profile_config(
        tmp_path,
        "dev",
        {
            "text_model": "dev-text-model",
            "vision_model": "dev-vision-model",
            "require_models": False,
        },
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("config.BACKEND_DIR", tmp_path)
    monkeypatch.delenv("APP_CONFIG_FILE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY_FILE", raising=False)
    monkeypatch.delenv("OPENAI_TEXT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_VISION_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_REQUIRE_MODELS", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.openai_text_model == "dev-text-model"
    assert settings.openai_vision_model == "dev-vision-model"
    assert settings.openai_require_models is False
    assert settings.openai_api_key is None
    assert settings.log_level == "WARNING"
    assert settings.log_file == "logs/dev.log"
    assert settings.log_to_console is False


def test_settings_load_selected_prod_profile(monkeypatch, tmp_path):
    write_profile_config(
        tmp_path,
        "prod",
        {
            "text_model": "prod-text-model",
            "vision_model": "prod-vision-model",
            "require_models": True,
        },
    )
    monkeypatch.setattr("config.BACKEND_DIR", tmp_path)
    monkeypatch.delenv("APP_CONFIG_FILE", raising=False)
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("OPENAI_TEXT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_VISION_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_REQUIRE_MODELS", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.openai_text_model == "prod-text-model"
    assert settings.openai_vision_model == "prod-vision-model"
    assert settings.openai_require_models is True
    assert settings.log_file == "logs/prod.log"


def test_environment_overrides_json(monkeypatch, tmp_path):
    config_file = write_config(
        tmp_path,
        {
            "text_model": "json-model",
            "require_models": True,
        },
    )
    monkeypatch.setenv("APP_CONFIG_FILE", str(config_file))
    monkeypatch.setenv("APP_ENV", "env")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_TEXT_MODEL", "environment-text-model")
    monkeypatch.setenv("OPENAI_VISION_MODEL", "environment-vision-model")
    monkeypatch.setenv("OPENAI_REQUIRE_MODELS", "false")
    monkeypatch.setenv("PROJECT_LOG_LEVEL", "debug")
    monkeypatch.setenv("PROJECT_LOG_FILE", "logs/environment.log")
    monkeypatch.setenv("PROJECT_LOG_TO_CONSOLE", "false")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.openai_api_key == "test-key"
    assert settings.openai_text_model == "environment-text-model"
    assert settings.openai_vision_model == "environment-vision-model"
    assert settings.openai_require_models is False
    assert settings.log_level == "DEBUG"
    assert settings.log_file == "logs/environment.log"
    assert settings.log_to_console is False


def test_invalid_json_configuration_is_rejected(monkeypatch, tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text("{invalid", encoding="utf-8")
    monkeypatch.setenv("APP_CONFIG_FILE", str(config_file))
    monkeypatch.delenv("APP_ENV", raising=False)
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="invalid JSON"):
        get_settings()


def test_api_key_can_be_loaded_from_secret_file(monkeypatch, tmp_path):
    config_file = write_config(
        tmp_path,
        {
            "text_model": "json-model",
            "require_models": True,
        },
    )
    secret_file = tmp_path / "openai_api_key"
    secret_file.write_text("file-based-test-key\n", encoding="utf-8")
    monkeypatch.setenv("APP_CONFIG_FILE", str(config_file))
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY_FILE", str(secret_file))
    get_settings.cache_clear()

    assert get_settings().openai_api_key == "file-based-test-key"


def test_invalid_app_env_is_rejected(monkeypatch, tmp_path):
    write_profile_config(
        tmp_path,
        "dev",
        {
            "text_model": "dev-text-model",
            "require_models": False,
        },
    )
    monkeypatch.setattr("config.BACKEND_DIR", tmp_path)
    monkeypatch.delenv("APP_CONFIG_FILE", raising=False)
    monkeypatch.setenv("APP_ENV", "staging")
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="APP_ENV"):
        get_settings()
