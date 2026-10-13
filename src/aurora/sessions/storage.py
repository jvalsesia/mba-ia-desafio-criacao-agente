from google.adk.sessions.schemas.v1 import Base
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncConnection

from aurora.sessions.service import (
    AuroraSessionService,
    SessionStoreError,
    translate_session_errors,
)

_TABLES = Base.metadata.tables
_SESSIONS = _TABLES["sessions"]
_CLEAR_ORDER = ("events", "sessions", "user_states", "app_states")


async def bootstrap_sessions(url: str) -> None:
    """Create the ADK session tables (idempotent); runs outside the uvicorn event loop."""
    try:
        service = AuroraSessionService(url)
    except ValueError:
        raise SessionStoreError() from None
    try:
        # Any public read makes the ADK create the tables and record the schema version.
        await service.get_session(app_name="aurora", user_id="bootstrap", session_id="bootstrap")
    except Exception as exc:
        raise SessionStoreError() from exc
    finally:
        try:
            await service.close()
        except Exception:  # noqa: BLE001
            pass


@translate_session_errors
async def clear_sessions(conn: AsyncConnection) -> int:
    """Delete sessions, events and states in the caller's transaction; return sessions removed."""
    present = {
        name
        for name in _CLEAR_ORDER
        if (await conn.execute(text("SELECT to_regclass(:n)"), {"n": name})).scalar() is not None
    }
    if "sessions" not in present:
        return 0
    count = (await conn.execute(select(func.count()).select_from(_SESSIONS))).scalar_one()
    for name in _CLEAR_ORDER:
        if name in present:
            await conn.execute(_TABLES[name].delete())
    return count
