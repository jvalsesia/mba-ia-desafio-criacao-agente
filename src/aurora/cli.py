import asyncio
import sys

import uvicorn

from aurora.config import API_HOST, API_PORT, ConfigError, load_settings
from aurora.db import DatabaseUnavailableError, wait_for_database
from aurora.main import create_app
from aurora.sessions.service import SessionStoreError
from aurora.sessions.storage import bootstrap_sessions
from aurora.store.errors import SeedDataError, StoreError
from aurora.store.seed import bootstrap_database


async def _wait_and_prepare(url: str) -> None:
    await wait_for_database(url)
    await bootstrap_database(url)
    await bootstrap_sessions(url)


def run_api() -> None:
    try:
        settings = load_settings()
        asyncio.run(_wait_and_prepare(settings.database_url))
    except (
        ConfigError,
        DatabaseUnavailableError,
        SeedDataError,
        StoreError,
        SessionStoreError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    uvicorn.run(create_app(settings), host=API_HOST, port=API_PORT)
