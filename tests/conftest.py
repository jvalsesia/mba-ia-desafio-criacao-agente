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


@pytest.fixture
def scripted():
    from types import SimpleNamespace

    from tests.scripted import ConfirmationTool, ScriptedModel

    return SimpleNamespace(
        main=ScriptedModel(), specialists=ScriptedModel(), confirmation=ConfirmationTool()
    )


def build_scripted_runner(scripted, session_service, engine, *, with_confirmation_tool=False):
    from aurora.agents.runtime import build_app, build_runner

    app = build_app(main_model=scripted.main, specialists_model=scripted.specialists, engine=engine)
    if with_confirmation_tool:
        reservations = app.root_agent.find_sub_agent("reservas")
        reservations.tools.append(scripted.confirmation.tool)
    return build_runner(app, session_service)


@pytest.fixture
def confirmation_tool_enabled():
    """Mark a test as needing `acao_com_confirmacao` on the `reservas` specialist."""
    return True


@pytest.fixture
async def conversation_client(client, scripted, request):
    with_tool = "confirmation_tool_enabled" in request.fixturenames
    client.app.state.runner = build_scripted_runner(
        scripted,
        client.app.state.session_service,
        client.app.state.engine,
        with_confirmation_tool=with_tool,
    )
    return client


@pytest.fixture
async def empty_session(no_sessions, engine):
    from aurora.sessions.service import open_session

    return await open_session(no_sessions, engine, apartment="101")


def _event(author, role, part, *, long_running=None):
    from google.adk.events.event import Event
    from google.genai import types

    return Event(
        author=author,
        invocation_id="inv-pending",
        content=types.Content(role=role, parts=[part]),
        long_running_tool_ids={long_running} if long_running else None,
    )


def _tool_call(author, call_id, name, args):
    from google.genai import types

    return _event(
        author,
        "model",
        types.Part(function_call=types.FunctionCall(id=call_id, name=name, args=args)),
    )


def _confirmation_request(author, conf_id, original, hint, payload=None):
    from google.genai import types

    confirmation = {"hint": hint, "confirmed": False}
    if payload is not None:
        confirmation["payload"] = payload
    part = types.Part(
        function_call=types.FunctionCall(
            id=conf_id,
            name="adk_request_confirmation",
            args={"originalFunctionCall": original, "toolConfirmation": confirmation},
        )
    )
    return _event(author, "user", part, long_running=conf_id)


def _tool_result(author, call_id, name):
    from google.genai import types

    part = types.Part(
        function_response=types.FunctionResponse(
            id=call_id,
            name=name,
            response={"error": "This tool call is rejected or awaiting confirmation."},
        )
    )
    return _event(author, "user", part)


def _user_text(text):
    from google.genai import types

    return _event("user", "user", types.Part(text=text))


def pending_events():
    booking = {"area": "salao-de-festas", "data": "2030-04-20"}
    guest = {"nome": "Joana Ribeiro", "data": "2030-04-21"}
    return [
        _user_text("Reserve o salão de festas para 2030-04-20."),
        _tool_call("reservas", "adk-fc-reserva", "reservar_area", booking),
        _confirmation_request(
            "reservas",
            "adk-conf-reserva",
            {"id": "adk-fc-reserva", "name": "reservar_area", "args": booking},
            "Reserva com taxa",
            {**booking, "taxa": 150.0},
        ),
        _tool_result("reservas", "adk-fc-reserva", "reservar_area"),
        _user_text("Libere a entrada da Joana Ribeiro no dia 2030-04-21."),
        _tool_call("visitantes", "adk-fc-visita", "autorizar_visitante", guest),
        _confirmation_request(
            "visitantes",
            "adk-conf-visita",
            {"id": "adk-fc-visita", "name": "autorizar_visitante", "args": guest},
            "Liberação de acesso",
        ),
        _tool_result("visitantes", "adk-fc-visita", "autorizar_visitante"),
    ]


def answered_event():
    from google.genai import types

    return _event(
        "user",
        "user",
        types.Part(
            function_response=types.FunctionResponse(
                id="adk-conf-reserva",
                name="adk_request_confirmation",
                response={"confirmed": False},
            )
        ),
    )


@pytest.fixture
async def session_with_pending(no_sessions, engine):
    from aurora.sessions.service import open_session

    session = await open_session(no_sessions, engine, apartment="101")
    for event in pending_events():
        await no_sessions.append_event(session, event)
    return session


@pytest.fixture
async def session_with_answered(no_sessions, engine):
    from aurora.sessions.service import open_session

    session = await open_session(no_sessions, engine, apartment="101")
    for event in [*pending_events(), answered_event()]:
        await no_sessions.append_event(session, event)
    return session


OFFLINE_DATABASE_URL = "postgresql+asyncpg://aurora:aurora@localhost:5999/aurora_test"


def _tool_map(tools):
    return {t.name: t.func for t in tools}


@pytest.fixture
async def reservation_tools(seeded):
    """The five reservation tools over the `aurora_test` engine, by name (plain coroutines)."""
    from aurora.agents.reservation_tools import build_reservation_tools

    return _tool_map(build_reservation_tools(seeded))


@pytest.fixture
def tool_context_for(session_service):
    """Build an ADK tool context for a session, optionally carrying a confirmation answer."""
    from google.adk.agents import LlmAgent
    from google.adk.agents.context import Context
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.tools.tool_confirmation import ToolConfirmation

    def build(session, confirmed=None, state=None):
        if state is not None:
            session = session.model_copy(update={"state": state})
        invocation = InvocationContext(
            session_service=session_service,
            invocation_id="inv-tool",
            agent=LlmAgent(name="reservas", model="scripted"),
            session=session,
        )
        answer = None if confirmed is None else ToolConfirmation(confirmed=confirmed)
        return Context(invocation, function_call_id="fc-tool", tool_confirmation=answer)

    return build


@pytest.fixture
async def session_201(no_sessions, engine):
    from aurora.sessions.service import open_session

    return await open_session(no_sessions, engine, apartment="201")


@pytest.fixture
async def offline_engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    eng = create_async_engine(OFFLINE_DATABASE_URL)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest.fixture
def offline_reservation_tools(offline_engine):
    from aurora.agents.reservation_tools import build_reservation_tools

    return _tool_map(build_reservation_tools(offline_engine))


@pytest.fixture
async def visitor_tools(seeded):
    """The two visitor tools over the `aurora_test` engine, by name (plain coroutines)."""
    from aurora.agents.visitor_tools import build_visitor_tools

    return _tool_map(build_visitor_tools(seeded))


@pytest.fixture
def offline_visitor_tools(offline_engine):
    from aurora.agents.visitor_tools import build_visitor_tools

    return _tool_map(build_visitor_tools(offline_engine))


@pytest.fixture(scope="session")
def bylaws():
    """The bylaws loaded from `dados/` by `load_bylaws`."""
    from aurora.agents.bylaws_document import load_bylaws

    return load_bylaws()


@pytest.fixture
def bylaws_tools(bylaws):
    """The bylaws tool built over `bylaws`, by name (plain coroutines)."""
    from aurora.agents.bylaws_tools import build_bylaws_tools

    return _tool_map(build_bylaws_tools(bylaws))
