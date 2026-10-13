import os

import pytest

os.environ["GOOGLE_API_KEY"] = "test-key"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://aurora:aurora@localhost:5432/aurora_test"

TEST_DATABASE_URL = os.environ["DATABASE_URL"]

CONFIG_VARS = ("GOOGLE_API_KEY", "GEMINI_MODEL_MAIN", "GEMINI_MODEL_SPECIALISTS", "DATABASE_URL")


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    from aurora.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def clean_env(monkeypatch):
    for name in CONFIG_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch
