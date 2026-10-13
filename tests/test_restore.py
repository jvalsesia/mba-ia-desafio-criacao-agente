import hashlib
import inspect
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

import aurora.restore as restore_module
from aurora.config import DATA_DIR
from aurora.restore import RestoreSummary, restore_data
from aurora.sessions.service import SessionStoreError, find_session, open_session
from aurora.store.errors import SeedDataError, StoreError
from aurora.store.reservations import cancel_reservation, create_reservation
from aurora.store.visitors import create_visitor
from tests.conftest import TEST_DATABASE_URL

FIXTURES = Path(__file__).parent / "fixtures"
SEED_RESERVATIONS = [
    ("RSV-1377", "101", "quadra", date(2030, 3, 9), "active"),
    ("RSV-2950", "201", "churrasqueira", date(2030, 3, 23), "active"),
    ("RSV-4821", "302", "salao-de-festas", date(2030, 3, 16), "active"),
]
SEED_VISITORS = [
    ("201", "Paulo Nogueira", date(2030, 3, 23)),
    ("302", "Marina Duarte", date(2030, 3, 16)),
]


async def read_state(engine):
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text("SELECT code, apartment, area_id, day, status FROM reservations ORDER BY code")
            )
        ).all()
        vis = (
            await conn.execute(
                text("SELECT apartment, name, day FROM visitors ORDER BY apartment, name")
            )
        ).all()
        seq = (
            await conn.execute(text("SELECT last_value, is_called FROM reservation_code_seq"))
        ).one()
    return [tuple(r) for r in rows], [tuple(v) for v in vis], tuple(seq)


async def count(engine, table):
    async with engine.connect() as conn:
        return (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()


@pytest.fixture
async def changed_state(seeded):
    await cancel_reservation(seeded, apartment="101", code="RSV-1377")
    await create_reservation(seeded, apartment="101", area_id="quadra", day=date(2030, 4, 6))
    await create_visitor(seeded, apartment="101", name="Joana Ribeiro", day=date(2030, 4, 21))
    return seeded


@pytest.fixture
async def two_sessions(session_with_history, no_sessions, engine):
    other = await open_session(no_sessions, engine, apartment="201")
    return session_with_history, other


async def test_restore_returns_data_to_seed_content(changed_state):
    summary = await restore_data(TEST_DATABASE_URL)
    reservations, visitors, _ = await read_state(changed_state)
    assert reservations == SEED_RESERVATIONS
    assert visitors == SEED_VISITORS
    assert (summary.reservations, summary.visitors) == (3, 2)


async def test_restore_removes_cancelled_rows(changed_state):
    await restore_data(TEST_DATABASE_URL)
    reservations, _, _ = await read_state(changed_state)
    assert all(r[4] != "cancelled" for r in reservations)
    assert max(r[0] for r in reservations) == "RSV-4821"


async def test_restore_restarts_code_sequence(changed_state):
    await restore_data(TEST_DATABASE_URL)
    created = await create_reservation(
        changed_state, apartment="101", area_id="quadra", day=date(2030, 5, 1)
    )
    assert created.code == "RSV-4822"


async def test_restore_removes_sessions_and_counts_them(changed_state, two_sessions, no_sessions):
    summary = await restore_data(TEST_DATABASE_URL)
    assert summary.sessions == 2
    for session in two_sessions:
        assert await find_session(no_sessions, session_id=session.id) is None
    assert await count(changed_state, "events") == 0


async def test_restore_keeps_session_tables_and_schema_version(changed_state, two_sessions):
    await restore_data(TEST_DATABASE_URL)
    async with changed_state.connect() as conn:
        for name in ("sessions", "events", "app_states", "user_states", "adk_internal_metadata"):
            found = (await conn.execute(text("SELECT to_regclass(:n)"), {"n": name})).scalar()
            assert found is not None
    assert await count(changed_state, "adk_internal_metadata") == 1


async def test_restore_twice_gives_same_state(changed_state, two_sessions):
    await restore_data(TEST_DATABASE_URL)
    first = await read_state(changed_state)
    second_summary = await restore_data(TEST_DATABASE_URL)
    assert (second_summary.reservations, second_summary.visitors, second_summary.sessions) == (
        3,
        2,
        0,
    )
    assert await read_state(changed_state) == first


async def test_restore_on_empty_database_creates_condo_schema(empty_database, no_session_tables):
    summary = await restore_data(TEST_DATABASE_URL)
    assert summary == RestoreSummary(3, 2, 0)
    assert await count(empty_database, "apartments") == 6
    assert await count(empty_database, "areas") == 3
    async with empty_database.connect() as conn:
        assert (await conn.execute(text("SELECT to_regclass('sessions')"))).scalar() is None


async def test_restore_without_session_tables(seeded, no_session_tables):
    summary = await restore_data(TEST_DATABASE_URL)
    assert summary.sessions == 0


async def test_restore_midway_failure_rolls_back_everything(changed_state, two_sessions):
    before = await read_state(changed_state)
    with pytest.raises(StoreError):
        await restore_data(TEST_DATABASE_URL, FIXTURES / "seed_overflow")
    assert await read_state(changed_state) == before
    assert await count(changed_state, "sessions") == 2
    assert await count(changed_state, "events") == 4


async def test_restore_invalid_seed_changes_nothing(changed_state, two_sessions):
    before = await read_state(changed_state)
    with pytest.raises(SeedDataError, match="reservas.json"):
        await restore_data(TEST_DATABASE_URL, FIXTURES / "seed_malformed")
    assert await read_state(changed_state) == before
    assert await count(changed_state, "sessions") == 2


async def test_restore_session_failure_rolls_back_data(changed_state, monkeypatch):
    async def failing(conn):
        raise SessionStoreError()

    before = await read_state(changed_state)
    monkeypatch.setattr(restore_module, "clear_sessions", failing)
    with pytest.raises(SessionStoreError):
        await restore_data(TEST_DATABASE_URL)
    assert await read_state(changed_state) == before


async def test_restore_unreachable_database_raises_store_error():
    url = "postgresql+asyncpg://aurora:segredo@localhost:5999/aurora"
    with pytest.raises(StoreError) as info:
        await restore_data(url)
    assert "segredo" not in str(info.value)


async def test_restore_does_not_touch_dados(seeded):
    def snapshot():
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA_DIR.iterdir()}

    before = snapshot()
    await restore_data(TEST_DATABASE_URL)
    assert snapshot() == before


async def test_restore_with_app_running_turns_sessions_into_404(client):
    created = await client.post("/sessoes", json={"apartamento": "101"})
    session_id = created.json()["session_id"]
    assert (await client.get(f"/sessoes/{session_id}/eventos")).status_code == 200
    summary = await restore_data(TEST_DATABASE_URL)
    assert summary.sessions == 1
    assert (await client.get(f"/sessoes/{session_id}/eventos")).status_code == 404
    assert (await client.post("/sessoes", json={"apartamento": "101"})).status_code == 201


def test_module_does_not_import_model():
    source = inspect.getsource(restore_module)
    assert "google.genai" not in source
    assert "AuroraSessionService" not in source
