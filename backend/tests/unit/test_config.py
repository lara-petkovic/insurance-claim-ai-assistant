import json

import pytest

from config import ConfigurationError, get_settings


def write_config(tmp_path, model):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"model": model}), encoding="utf-8")
    return config_file


def test_settings_load_from_json(monkeypatch, tmp_path):
    config_file = write_config(
        tmp_path,
        {
            "provider": "openai",
            "text_model": "json-text-model",
            "vision_model": "json-vision-model",
            "require_models": True,
        },
    )
    monkeypatch.setenv("APP_CONFIG_FILE", str(config_file))
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY_FILE", raising=False)
    monkeypatch.delenv("OPENAI_TEXT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_VISION_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_REQUIRE_MODELS", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.model_provider == "openai"
    assert settings.openai_text_model == "json-text-model"
    assert settings.openai_vision_model == "json-vision-model"
    assert settings.openai_require_models is True
    assert settings.openai_api_key is None


def test_environment_overrides_json(monkeypatch, tmp_path):
    config_file = write_config(
        tmp_path,
        {
            "provider": "openai",
            "text_model": "json-model",
            "require_models": True,
        },
    )
    monkeypatch.setenv("APP_CONFIG_FILE", str(config_file))
    monkeypatch.setenv("MODEL_PROVIDER", "custom")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_TEXT_MODEL", "environment-text-model")
    monkeypatch.setenv("OPENAI_VISION_MODEL", "environment-vision-model")
    monkeypatch.setenv("OPENAI_REQUIRE_MODELS", "false")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.model_provider == "custom"
    assert settings.openai_api_key == "test-key"
    assert settings.openai_text_model == "environment-text-model"
    assert settings.openai_vision_model == "environment-vision-model"
    assert settings.openai_require_models is False


def test_invalid_json_configuration_is_rejected(monkeypatch, tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text("{invalid", encoding="utf-8")
    monkeypatch.setenv("APP_CONFIG_FILE", str(config_file))
    get_settings.cache_clear()

    with pytest.raises(ConfigurationError, match="invalid JSON"):
        get_settings()


def test_api_key_can_be_loaded_from_secret_file(monkeypatch, tmp_path):
    config_file = write_config(
        tmp_path,
        {
            "provider": "openai",
            "text_model": "json-model",
            "require_models": True,
        },
    )
    secret_file = tmp_path / "openai_api_key"
    secret_file.write_text("file-based-test-key\n", encoding="utf-8")
    monkeypatch.setenv("APP_CONFIG_FILE", str(config_file))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY_FILE", str(secret_file))
    get_settings.cache_clear()

    assert get_settings().openai_api_key == "file-based-test-key"
