import asyncio
import time

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from aurora.config import Settings


class DatabaseUnavailableError(Exception):
    """The database did not answer within the allowed time."""


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(settings.database_url, pool_pre_ping=True)


def describe_target(url: str) -> str:
    parsed = make_url(url)
    return f"{parsed.host}:{parsed.port or 5432} (database {parsed.database})"


async def _ping(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


async def wait_for_database(
    url: str, timeout_seconds: float = 10, interval_seconds: float = 1
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            await _ping(url)
            return
        except Exception:
            if time.monotonic() + interval_seconds >= deadline:
                break
            await asyncio.sleep(interval_seconds)
    parsed = make_url(url)
    raise DatabaseUnavailableError(
        f"Banco de dados inacessível em {parsed.host}:{parsed.port or 5432} "
        f"(database {parsed.database}) após {timeout_seconds:g} s. "
        'Suba o Postgres com "docker compose up -d".'
    )
