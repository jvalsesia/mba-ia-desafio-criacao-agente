import asyncio
import sys

import uvicorn

from aurora.config import API_HOST, API_PORT, ConfigError, load_settings
from aurora.db import DatabaseUnavailableError, wait_for_database
from aurora.main import create_app


def run_api() -> None:
    try:
        settings = load_settings()
        asyncio.run(wait_for_database(settings.database_url))
    except (ConfigError, DatabaseUnavailableError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    uvicorn.run(create_app(settings), host=API_HOST, port=API_PORT)
