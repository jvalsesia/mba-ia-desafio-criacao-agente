import pytest
from google.genai import types

from aurora.conversation.service import (
    APOLOGY_MESSAGE,
    ASSISTANT_UNAVAILABLE_MESSAGE,
    NO_REPLY_MESSAGE,
    AssistantUnavailableError,
    run_turn,
    send_message,
)
from aurora.sessions.service import find_session, session_apartment
from tests import scripted as sc
from tests.conftest import build_scripted_runner


@pytest.fixture
def runner(scripted, session_service):
    return build_scripted_runner(scripted, session_service)


async def _events(service, session):
    return (await find_session(service, session_id=session.id)).events


async def test_text_turn_returns_reply_and_no_pending(
    scripted, runner, session_service, empty_session
):
    scripted.main.script(sc.text("Olá! Sou o assistente do Residencial Aurora."))
    result = await send_message(runner, session_service, empty_session, text="Olá")
    assert result.reply == "Olá! Sou o assistente do Residencial Aurora."
    assert result.pending == []
    reread = await find_session(session_service, session_id=empty_session.id)
    assert len(reread.events) == 2
    assert session_apartment(reread) == "101"


async def test_turn_through_sub_agent_returns_specialist_text(
    scripted, runner, session_service, empty_session
):
    scripted.main.script(sc.transfer("reservas"))
    scripted.specialists.script(sc.text("Ainda não consigo consultar reservas."))
    result = await send_message(runner, session_service, empty_session, text="Minhas reservas?")
    assert result.reply == "Ainda não consigo consultar reservas."
    events = await _events(session_service, empty_session)
    assert events[-1].author == "reservas"


async def test_next_turn_starts_at_the_assistant(scripted, runner, session_service, empty_session):
    scripted.main.script(sc.transfer("reservas"), sc.text("Posso ajudar."))
    scripted.specialists.script(sc.text("Ainda não consigo."))
    await send_message(runner, session_service, empty_session, text="Minhas reservas?")
    result = await send_message(runner, session_service, empty_session, text="O que você faz?")
    assert result.reply == "Posso ajudar."
    assert scripted.specialists.calls == 1


async def test_turn_through_bylaws_tool(scripted, runner, session_service, empty_session):
    scripted.main.script(sc.tool_call("regulamento", {"request": "piscina?"}), sc.text("Fim."))
    scripted.specialists.script(sc.text("Sem acesso."))
    result = await send_message(runner, session_service, empty_session, text="Piscina?")
    assert result.reply == "Fim."
    events = await _events(session_service, empty_session)
    assert all(e.author != "regulamento" for e in events)


async def test_turn_with_pending_keeps_the_list(
    scripted, runner, session_service, session_with_pending
):
    scripted.main.script(sc.text("Olá! Como posso ajudar?"))
    result = await send_message(runner, session_service, session_with_pending, text="Olá")
    assert [p.id for p in result.pending] == ["adk-conf-reserva", "adk-conf-visita"]


async def test_paused_turn_returns_empty_reply(scripted, session_service, empty_session):
    runner = build_scripted_runner(scripted, session_service, with_confirmation_tool=True)
    scripted.main.script(sc.transfer("reservas"))
    scripted.specialists.script(sc.tool_call("acao_com_confirmacao", {"descricao": "teste"}))
    result = await send_message(runner, session_service, empty_session, text="Execute.")
    assert result.reply == ""
    assert len(result.pending) == 1
    assert result.pending[0].action == "acao_com_confirmacao"
    assert result.pending[0].details == {"descricao": "teste"}
    assert scripted.confirmation.executions == []


async def test_turn_without_text_returns_fallback(scripted, runner, session_service, empty_session):
    scripted.main.script(sc.empty_text())
    result = await send_message(runner, session_service, empty_session, text="Olá")
    assert result.reply == NO_REPLY_MESSAGE


async def test_unknown_tool_returns_apology(scripted, runner, session_service, empty_session):
    scripted.main.script(sc.tool_call("ferramenta_inexistente"))
    result = await send_message(runner, session_service, empty_session, text="Olá")
    assert result.reply == APOLOGY_MESSAGE
    assert result.pending == []


async def test_apology_keeps_pending(scripted, runner, session_service, session_with_pending):
    scripted.main.script(sc.tool_call("ferramenta_inexistente"))
    result = await send_message(runner, session_service, session_with_pending, text="Olá")
    assert result.reply == APOLOGY_MESSAGE
    assert [p.id for p in result.pending] == ["adk-conf-reserva", "adk-conf-visita"]


@pytest.mark.parametrize("failure", [sc.quota_error, sc.service_error, sc.connection_error])
async def test_model_failures_raise_unavailable(
    failure, scripted, runner, session_service, empty_session
):
    scripted.main.script(failure())
    with pytest.raises(AssistantUnavailableError) as info:
        await send_message(runner, session_service, empty_session, text="Olá")
    assert str(info.value) == ASSISTANT_UNAVAILABLE_MESSAGE


async def test_unavailable_message_has_no_internal_data(
    scripted, runner, session_service, empty_session
):
    scripted.main.script(sc.quota_error())
    with pytest.raises(AssistantUnavailableError) as info:
        await send_message(runner, session_service, empty_session, text="Olá")
    assert "test-key" not in str(info.value)
    assert "quota exceeded" not in str(info.value)


async def test_turn_after_failure_works(scripted, runner, session_service, empty_session):
    scripted.main.script(sc.quota_error(), sc.text("Olá! Como posso ajudar?"))
    with pytest.raises(AssistantUnavailableError):
        await send_message(runner, session_service, empty_session, text="Olá")
    result = await send_message(runner, session_service, empty_session, text="Olá de novo")
    assert result.reply == "Olá! Como posso ajudar?"


async def test_run_turn_accepts_a_content_message(scripted, runner, session_service, empty_session):
    scripted.main.script(sc.text("Ok."))
    message = types.Content(role="user", parts=[types.Part(text="Oi")])
    result = await run_turn(runner, session_service, empty_session, message)
    assert result.reply == "Ok."


async def test_turn_survives_new_runner(scripted, runner, session_service, empty_session):
    from aurora.sessions.service import AuroraSessionService
    from tests.conftest import TEST_DATABASE_URL

    scripted.main.script(sc.text("Primeira."), sc.text("Segunda."))
    await send_message(runner, session_service, empty_session, text="Um")
    other = AuroraSessionService(TEST_DATABASE_URL)
    try:
        new_runner = build_scripted_runner(scripted, other)
        assert len(await _events(other, empty_session)) == 2
        await send_message(new_runner, other, empty_session, text="Dois")
        assert len(await _events(other, empty_session)) == 4
    finally:
        await other.close()
