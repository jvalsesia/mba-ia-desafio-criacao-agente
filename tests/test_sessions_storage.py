import pytest
from google.adk.events.event import Event
from google.genai import types
from sqlalchemy import text

from aurora.sessions.service import (
    AuroraSessionService,
    SessionStoreError,
    find_session,
    open_session,
)
from aurora.sessions.storage import bootstrap_sessions, clear_sessions
from tests.conftest import TEST_DATABASE_URL

TABLES = {"sessions", "events", "app_states", "user_states", "adk_internal_metadata"}


async def existing_tables(engine):
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        )
        return {r[0] for r in rows} & TABLES


async def test_bootstrap_creates_session_tables(no_session_tables, engine):
    assert await existing_tables(engine) == set()
    await bootstrap_sessions(TEST_DATABASE_URL)
    assert await existing_tables(engine) == TABLES


async def test_bootstrap_is_idempotent(session_with_history, engine):
    await bootstrap_sessions(TEST_DATABASE_URL)
    await bootstrap_sessions(TEST_DATABASE_URL)
    s = await find_session(
        session_with_history and AuroraSessionService(TEST_DATABASE_URL),
        session_id=session_with_history.id,
    )
    assert len(s.events) == 4


async def test_bootstrap_unreachable_database_raises():
    with pytest.raises(SessionStoreError) as info:
        await bootstrap_sessions("postgresql+asyncpg://aurora:segredo@localhost:5999/x")
    assert "segredo" not in str(info.value)


async def test_clear_sessions_removes_everything_and_counts(
    session_with_history, no_sessions, engine
):
    await open_session(no_sessions, engine, apartment="201")
    async with engine.begin() as conn:
        assert await clear_sessions(conn) == 2
    async with engine.connect() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM sessions"))).scalar_one() == 0
        assert (await conn.execute(text("SELECT count(*) FROM events"))).scalar_one() == 0


async def test_clear_sessions_twice_returns_zero(session_with_history, engine):
    async with engine.begin() as conn:
        await clear_sessions(conn)
    async with engine.begin() as conn:
        assert await clear_sessions(conn) == 0


async def test_clear_sessions_without_tables_returns_zero(no_session_tables, engine):
    async with engine.begin() as conn:
        assert await clear_sessions(conn) == 0


async def test_clear_sessions_rollback_keeps_sessions(session_with_history, no_sessions, engine):
    other = await open_session(no_sessions, engine, apartment="201")
    conn = await engine.connect()
    trans = await conn.begin()
    await clear_sessions(conn)
    await trans.rollback()
    await conn.close()
    s = await find_session(no_sessions, session_id=session_with_history.id)
    assert len(s.events) == 4
    assert await find_session(no_sessions, session_id=other.id) is not None


async def test_clear_sessions_keeps_schema_version(session_with_history, no_sessions, engine):
    async with engine.begin() as conn:
        await clear_sessions(conn)
    s = await open_session(no_sessions, engine, apartment="101")
    assert s.id
    async with engine.connect() as conn:
        n = (await conn.execute(text("SELECT count(*) FROM adk_internal_metadata"))).scalar_one()
    assert n >= 1


async def test_cleared_session_id_is_not_found(session_with_history, no_sessions, engine):
    async with engine.begin() as conn:
        await clear_sessions(conn)
    assert await find_session(no_sessions, session_id=session_with_history.id) is None


_ = (Event, types)
