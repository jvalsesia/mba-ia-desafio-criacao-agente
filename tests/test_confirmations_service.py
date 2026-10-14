import pytest

from aurora.conversation.confirmations import (
    APPROVED_MESSAGE,
    DENIED_MESSAGE,
    NOT_EXECUTED_MESSAGE,
    answer_confirmation,
)
from aurora.conversation.pending import confirmation_result
from aurora.sessions.service import SessionStoreError, find_session, session_apartment
from tests import scripted as sc
from tests.conftest import build_scripted_resume_runners
from tests.test_reservation_tools import SEED_CODES, active, codes

DENIED = "A reserva não foi confirmada. Nada foi alterado."


@pytest.fixture
def runners(scripted, session_service, engine):
    return build_scripted_resume_runners(scripted, session_service, engine)


async def answer(runners, service, session, confirmation_id, confirmed=True):
    return await answer_confirmation(
        runners, service, session, confirmation_id=confirmation_id, confirmed=confirmed
    )


async def reread(service, session):
    return await find_session(service, session_id=session.id)


async def test_unknown_id_returns_nothing(runners, scripted, session_service, session_with_pending):
    result = await answer(runners, session_service, session_with_pending, "desconhecido")
    assert result is None
    current = await reread(session_service, session_with_pending)
    assert len(current.events) == 8
    assert scripted.specialists.calls == 0


async def test_approval_runs_the_held_tool(
    runners, scripted, session_service, session_with_pending, engine
):
    scripted.specialists.script(sc.text("Reserva confirmada."))
    result = await answer(runners, session_service, session_with_pending, "adk-conf-reserva")
    assert result.reply == "Reserva confirmada."
    assert [p.id for p in result.pending] == ["adk-conf-visita"]
    assert len(await active(engine, apartment="101", area_id="salao-de-festas")) == 1


async def test_answer_is_delivered_to_the_requesting_specialist(
    runners, scripted, session_service, session_with_pending
):
    scripted.specialists.script(sc.text("Reserva confirmada."))
    await answer(runners, session_service, session_with_pending, "adk-conf-reserva")
    events = (await reread(session_service, session_with_pending)).events[8:]
    assert events[0].author == "user"
    assert {e.author for e in events[1:]} == {"reservas"}
    assert scripted.main.calls == 0


async def test_denial_writes_nothing(runners, scripted, session_service, session_with_pending):
    scripted.specialists.script(sc.text(DENIED))
    result = await answer(runners, session_service, session_with_pending, "adk-conf-reserva", False)
    assert result.reply == DENIED
    current = await reread(session_service, session_with_pending)
    assert confirmation_result(current, "adk-conf-reserva")["status"] == "nao_confirmada"


async def test_visitor_approval(runners, scripted, session_service, session_with_pending, engine):
    scripted.specialists.script(sc.text("Autorizada."))
    await answer(runners, session_service, session_with_pending, "adk-conf-visita")
    current = await reread(session_service, session_with_pending)
    assert confirmation_result(current, "adk-conf-visita")["status"] == "autorizado"


async def test_request_without_payload_resumes_with_original_arguments(
    runners, scripted, session_service, session_with_pending, engine
):
    from sqlalchemy import text

    scripted.specialists.script(sc.text("Autorizada."))
    await answer(runners, session_service, session_with_pending, "adk-conf-visita")
    async with engine.connect() as conn:
        rows = (
            await conn.execute(text("SELECT name, day::text FROM visitors WHERE apartment='101'"))
        ).all()
    assert [tuple(r) for r in rows] == [("Joana Ribeiro", "2030-04-21")]


async def test_model_failure_after_tool_uses_result_message(
    runners, scripted, session_service, session_201, session_with_pending, engine
):
    async with engine.begin() as conn:
        from sqlalchemy import text

        await conn.execute(
            text(
                "INSERT INTO reservations (code, apartment, area_id, day) "
                "VALUES ('RSV-9001', '201', 'salao-de-festas', '2030-04-20')"
            )
        )
    scripted.specialists.script(sc.quota_error())
    result = await answer(runners, session_service, session_with_pending, "adk-conf-reserva")
    assert result.reply == "Essa data não está mais disponível."
    assert [p.id for p in result.pending] == ["adk-conf-visita"]


async def test_model_failure_after_approval_uses_fixed_text(
    runners, scripted, session_service, session_with_pending, engine
):
    scripted.specialists.script(sc.quota_error())
    result = await answer(runners, session_service, session_with_pending, "adk-conf-reserva")
    assert result.reply == APPROVED_MESSAGE
    assert len(await active(engine, apartment="101", area_id="salao-de-festas")) == 1


@pytest.mark.usefixtures("confirmation_tool_enabled")
async def test_denial_without_message_uses_fixed_text(
    scripted, session_service, engine, empty_session
):
    from tests.conftest import build_scripted_runner

    runner = build_scripted_runner(scripted, session_service, engine, with_confirmation_tool=True)
    resume = build_scripted_resume_runners(
        scripted, session_service, engine, with_confirmation_tool=True
    )
    from google.genai import types

    from aurora.conversation.service import execute_turn

    scripted.main.script(sc.transfer("reservas"))
    scripted.specialists.script(sc.tool_call("acao_com_confirmacao", {"descricao": "x"}))
    msg = types.Content(role="user", parts=[types.Part(text="Execute.")])
    await execute_turn(runner, empty_session, msg)
    current = await reread(session_service, empty_session)
    from aurora.conversation.pending import pending_confirmations

    p = pending_confirmations(current)[0]
    scripted.specialists.script(sc.empty_text())
    result = await answer(resume, session_service, current, p.id, False)
    assert result.reply == DENIED_MESSAGE


async def test_empty_model_text_uses_fallback(
    runners, scripted, session_service, session_with_pending
):
    scripted.specialists.script(sc.empty_text())
    result = await answer(runners, session_service, session_with_pending, "adk-conf-reserva")
    assert result.reply == APPROVED_MESSAGE


@pytest.mark.usefixtures("confirmation_tool_enabled")
async def test_failed_resume_keeps_item_pending_and_second_answer_executes_once(
    scripted, session_service, engine, empty_session
):
    from google.genai import types

    from aurora.conversation.pending import pending_confirmations
    from aurora.conversation.service import execute_turn
    from tests.conftest import build_scripted_runner

    runner = build_scripted_runner(scripted, session_service, engine, with_confirmation_tool=True)
    resume = build_scripted_resume_runners(
        scripted, session_service, engine, with_confirmation_tool=True
    )
    scripted.main.script(sc.transfer("reservas"))
    scripted.specialists.script(sc.tool_call("acao_com_confirmacao", {"descricao": "x"}))
    msg = types.Content(role="user", parts=[types.Part(text="Execute.")])
    await execute_turn(runner, empty_session, msg)
    p = pending_confirmations(await reread(session_service, empty_session))[0]

    scripted.confirmation.fail_next = True
    result = await answer(
        resume, session_service, await reread(session_service, empty_session), p.id
    )
    assert result.reply == NOT_EXECUTED_MESSAGE
    assert [i.id for i in result.pending] == [p.id]
    assert scripted.confirmation.executions == []

    scripted.specialists.script(sc.text("Feito."))
    result = await answer(
        resume, session_service, await reread(session_service, empty_session), p.id
    )
    assert result.reply == "Feito."
    assert result.pending == []
    assert scripted.confirmation.executions == ["x"]


async def test_unfinished_answer_can_be_answered(
    runners, scripted, session_service, session_with_unfinished_answer, engine
):
    scripted.specialists.script(sc.text("Reserva confirmada."))
    result = await answer(
        runners, session_service, session_with_unfinished_answer, "adk-conf-reserva"
    )
    assert result.reply == "Reserva confirmada."
    assert [p.id for p in result.pending] == ["adk-conf-visita"]
    assert len(await active(engine, apartment="101", area_id="salao-de-festas")) == 1


async def test_missing_resume_runner_keeps_item_pending(
    scripted, session_service, session_with_pending
):
    result = await answer({}, session_service, session_with_pending, "adk-conf-reserva")
    assert result.reply == NOT_EXECUTED_MESSAGE
    assert [p.id for p in result.pending] == ["adk-conf-reserva", "adk-conf-visita"]
    assert len((await reread(session_service, session_with_pending)).events) == 8


async def test_store_failure_inside_tool_resolves_item(
    scripted, session_service, engine, offline_engine, session_with_pending
):
    runners = build_scripted_resume_runners(
        scripted, session_service, engine, tools_engine=offline_engine
    )
    scripted.specialists.script(sc.relay_tool_message)
    result = await answer(runners, session_service, session_with_pending, "adk-conf-reserva")
    assert result.reply == "Não consegui concluir o pedido agora. Tente novamente em instantes."
    assert [p.id for p in result.pending] == ["adk-conf-visita"]
    current = await reread(session_service, session_with_pending)
    assert confirmation_result(current, "adk-conf-reserva")["status"] == "servico_indisponivel"
    assert await codes(engine) == SEED_CODES


async def test_session_store_failure_propagates(runners, session_with_pending):
    class Broken:
        async def get_session(self, **kwargs):
            raise SessionStoreError()

    scripted_service = Broken()
    with pytest.raises(SessionStoreError):
        await answer(runners, scripted_service, session_with_pending, "adk-conf-reserva")


async def test_no_state_change_to_apartment(
    runners, scripted, session_service, session_with_pending
):
    scripted.specialists.script(sc.text("Reserva confirmada."))
    await answer(runners, session_service, session_with_pending, "adk-conf-reserva")
    current = await reread(session_service, session_with_pending)
    assert session_apartment(current) == "101"
