from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

from aurora.config import DATA_DIR
from aurora.sessions.storage import clear_sessions
from aurora.store.errors import translate_errors
from aurora.store.seed import reset_condo_data


@dataclass(frozen=True)
class RestoreSummary:
    reservations: int
    visitors: int
    sessions: int


@translate_errors
async def restore_data(url: str, data_dir: Path = DATA_DIR) -> RestoreSummary:
    """Clear sessions and reload the seed data in one transaction."""
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            sessions = await clear_sessions(conn)
            seeded = await reset_condo_data(conn, data_dir)
    finally:
        await engine.dispose()
    return RestoreSummary(seeded.reservations, seeded.visitors, sessions)
