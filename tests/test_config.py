import os

import pytest

from aurora.config import DEFAULT_DATABASE_URL, ConfigError, load_settings


def test_defaults_when_only_key_is_set(clean_env):
    clean_env.setenv("GOOGLE_API_KEY", "k")
    s = load_settings(env_file=None)
    assert s.gemini_model_main == "gemini-3.8-flash"
    assert s.gemini_model_specialists == "gemini-3.8-flash"
    assert s.database_url == DEFAULT_DATABASE_URL


def test_empty_values_fall_back_to_defaults(clean_env):
    clean_env.setenv("GOOGLE_API_KEY", "k")
    for name in ("GEMINI_MODEL_MAIN", "GEMINI_MODEL_SPECIALISTS", "DATABASE_URL"):
        clean_env.setenv(name, "")
    s = load_settings(env_file=None)
    assert s.gemini_model_main == "gemini-3.8-flash"
    assert s.gemini_model_specialists == "gemini-3.8-flash"
    assert s.database_url == DEFAULT_DATABASE_URL


def test_env_overrides_defaults(clean_env):
    url = "postgresql+asyncpg://aurora:aurora@localhost:5432/aurora_test"
    clean_env.setenv("GOOGLE_API_KEY", "test-key")
    clean_env.setenv("GEMINI_MODEL_MAIN", "modelo-a")
    clean_env.setenv("GEMINI_MODEL_SPECIALISTS", "modelo-b")
    clean_env.setenv("DATABASE_URL", url)
    s = load_settings(env_file=None)
    assert (s.gemini_model_main, s.gemini_model_specialists) == ("modelo-a", "modelo-b")
    assert s.database_url == url


def test_missing_key_raises_config_error(clean_env):
    with pytest.raises(ConfigError, match="GOOGLE_API_KEY"):
        load_settings(env_file=None)


def test_empty_key_raises_config_error(clean_env):
    clean_env.setenv("GOOGLE_API_KEY", "")
    with pytest.raises(ConfigError, match="GOOGLE_API_KEY"):
        load_settings(env_file=None)


def test_invalid_database_url_does_not_leak_value(clean_env):
    clean_env.setenv("GOOGLE_API_KEY", "test-key")
    clean_env.setenv("DATABASE_URL", "nao-e-url://usuario:segredo-teste@")
    with pytest.raises(ConfigError) as info:
        load_settings(env_file=None)
    assert "DATABASE_URL" in str(info.value)
    assert "segredo-teste" not in str(info.value)


def test_key_is_exported_to_environment(clean_env):
    clean_env.setenv("GOOGLE_API_KEY", "valor-xyz")
    s = load_settings(env_file=None)
    assert os.environ["GOOGLE_API_KEY"] == s.google_api_key == "valor-xyz"
