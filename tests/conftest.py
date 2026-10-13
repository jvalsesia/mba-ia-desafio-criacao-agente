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


@pytest.fixture
async def engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    eng = create_async_engine(TEST_DATABASE_URL)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture
async def seeded(engine):
    from aurora.store.seed import reset_condo_data

    async with engine.begin() as conn:
        await reset_condo_data(conn)
    return engine


@pytest.fixture
async def empty_database(engine):
    from aurora.store.schema import metadata

    async with engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)
    return engine
