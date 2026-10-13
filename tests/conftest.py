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


@pytest.fixture
async def session_service(seeded):
    from aurora.sessions.service import AuroraSessionService
    from aurora.sessions.storage import bootstrap_sessions

    await bootstrap_sessions(TEST_DATABASE_URL)
    service = AuroraSessionService(TEST_DATABASE_URL)
    try:
        yield service
    finally:
        await service.close()


@pytest.fixture
async def no_sessions(session_service, engine):
    from aurora.sessions.storage import clear_sessions

    async with engine.begin() as conn:
        await clear_sessions(conn)
    return session_service


async def append_history(service, session):
    from google.adk.events.event import Event
    from google.adk.events.event_actions import EventActions
    from google.adk.tools.tool_confirmation import ToolConfirmation
    from google.genai import types

    def part_event(author, role, part, actions=None):
        return Event(
            author=author,
            invocation_id="inv-1",
            content=types.Content(role=role, parts=[part]),
            actions=actions or EventActions(),
        )

    events = [
        part_event("user", "user", types.Part(text="Quais são as minhas reservas?")),
        part_event(
            "reservas",
            "model",
            types.Part(
                function_call=types.FunctionCall(id="fc-1", name="listar_minhas_reservas", args={})
            ),
        ),
        part_event(
            "reservas",
            "user",
            types.Part(
                function_response=types.FunctionResponse(
                    id="fc-1",
                    name="listar_minhas_reservas",
                    response={
                        "reservas": [{"codigo": "RSV-1377", "area": "quadra", "data": "2030-03-09"}]
                    },
                )
            ),
        ),
        part_event(
            "reservas",
            "model",
            types.Part(
                function_call=types.FunctionCall(
                    id="fc-2",
                    name="reservar_area",
                    args={"area": "salao-de-festas", "data": "2030-04-20"},
                )
            ),
            EventActions(
                requested_tool_confirmations={
                    "fc-2": ToolConfirmation(
                        hint="Reserva com taxa",
                        confirmed=False,
                        payload={"area": "salao-de-festas", "data": "2030-04-20", "taxa": 150.0},
                    )
                }
            ),
        ),
    ]
    for event in events:
        await service.append_event(session, event)


@pytest.fixture
async def session_with_history(no_sessions, engine):
    from aurora.sessions.service import open_session

    session = await open_session(no_sessions, engine, apartment="101")
    await append_history(no_sessions, session)
    return session


@pytest.fixture
async def no_session_tables(engine):
    from google.adk.sessions.schemas.v1 import Base
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP TABLE IF EXISTS adk_internal_metadata"))
    return engine


@pytest.fixture
async def client(seeded, no_sessions):
    import httpx

    from aurora.config import get_settings
    from aurora.main import create_app

    app = create_app(get_settings())
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            c.app = app
            yield c
