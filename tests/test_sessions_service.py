import inspect

import pytest
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.genai import types
from sqlalchemy import text

from aurora.sessions import service as service_module
from aurora.sessions.service import (
    APP_NAME,
    USER_ID,
    AuroraSessionService,
    SessionStoreError,
    find_session,
    open_session,
    session_apartment,
)
from tests.conftest import TEST_DATABASE_URL


def text_event(msg, author="user"):
    return Event(
        author=author,
        invocation_id="inv-x",
        content=types.Content(role="user", parts=[types.Part(text=msg)]),
    )


async def count_sessions(engine):
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT count(*) FROM sessions"))).scalar_one()


async def test_open_session_binds_apartment(no_sessions, engine):
    s = await open_session(no_sessions, engine, apartment="101")
    assert s.id
    assert session_apartment(s) == "101"
    again = await find_session(no_sessions, session_id=s.id)
    assert session_apartment(again) == "101" and again.events == []


async def test_open_session_unknown_apartment_returns_none(no_sessions, engine):
    assert await open_session(no_sessions, engine, apartment="999") is None
    assert await count_sessions(engine) == 0


async def test_open_session_generates_distinct_ids(no_sessions, engine):
    a = await open_session(no_sessions, engine, apartment="101")
    b = await open_session(no_sessions, engine, apartment="101")
    assert a.id != b.id


async def test_find_session_returns_events_in_order(session_with_history, no_sessions):
    s = await find_session(no_sessions, session_id=session_with_history.id)
    assert len(s.events) == 4
    assert [e.author for e in s.events] == ["user", "reservas", "reservas", "reservas"]
    assert s.events[0].content.parts[0].text == "Quais são as minhas reservas?"


async def test_find_session_unknown_returns_none(no_sessions):
    assert await find_session(no_sessions, session_id="sessao-inexistente") is None


async def test_append_event_drops_apartment_from_state_delta(no_sessions, engine):
    s = await open_session(no_sessions, engine, apartment="101")
    ev = text_event("oi")
    ev.actions = EventActions(state_delta={"apartamento": "302", "observacao": "x"})
    await no_sessions.append_event(s, ev)
    again = await find_session(no_sessions, session_id=s.id)
    assert session_apartment(again) == "101"
    assert again.state["observacao"] == "x"
    assert "apartamento" not in again.events[0].actions.state_delta


async def test_apartment_survives_new_service_instance(session_with_history, no_sessions):
    await no_sessions.close()
    other = AuroraSessionService(TEST_DATABASE_URL)
    try:
        s = await find_session(other, session_id=session_with_history.id)
        assert session_apartment(s) == "101" and len(s.events) == 4
    finally:
        await other.close()


async def test_append_after_new_service_instance_increases_count(session_with_history, no_sessions):
    await no_sessions.close()
    other = AuroraSessionService(TEST_DATABASE_URL)
    try:
        s = await find_session(other, session_id=session_with_history.id)
        await other.append_event(s, text_event("Quais são as minhas reservas agora?"))
        s = await find_session(other, session_id=session_with_history.id)
        assert len(s.events) == 5
        assert s.events[-1].content.parts[0].text == "Quais são as minhas reservas agora?"
    finally:
        await other.close()


async def test_sessions_of_different_apartments_are_independent(no_sessions, engine):
    a = await open_session(no_sessions, engine, apartment="101")
    b = await open_session(no_sessions, engine, apartment="201")
    await no_sessions.append_event(a, text_event("oi"))
    a = await find_session(no_sessions, session_id=a.id)
    b = await find_session(no_sessions, session_id=b.id)
    assert len(a.events) == 1 and b.events == []
    assert session_apartment(a) == "101" and session_apartment(b) == "201"


async def test_unreachable_database_raises_session_store_error(engine):
    bad = AuroraSessionService("postgresql+asyncpg://aurora:segredo@localhost:5999/aurora_test")
    try:
        with pytest.raises(SessionStoreError) as info:
            await find_session(bad, session_id="x")
        assert "segredo" not in str(info.value) and "SELECT" not in str(info.value)
    finally:
        await bad.close()


def test_no_operation_changes_the_apartment():
    assert (APP_NAME, USER_ID) == ("aurora", "morador")
    for name, fn in inspect.getmembers(service_module, inspect.isfunction):
        if fn.__module__ != service_module.__name__:
            continue
        params = set(inspect.signature(fn).parameters)
        if "apartment" in params:
            assert name == "open_session" and "session_id" not in params
            assert "session" not in params
