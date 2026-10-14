import asyncio
import json

import pytest
from sqlalchemy import text

from aurora.conversation.confirmations import (
    APPROVED_MESSAGE,
    NOT_EXECUTED_MESSAGE,
    NOT_PENDING_MESSAGE,
)
from tests import scripted as sc
from tests.test_reservation_tools import SEED_CODES, active, codes

HALL = {"area": "salao-de-festas", "data": "2030-04-20"}
GUEST = {"nome": "Joana Ribeiro", "data": "2030-04-21"}
DENIED = "A reserva não foi confirmada. Nada foi alterado."


async def say(client, session, texto):
    return await client.post(f"/sessoes/{session.id}/mensagens", json={"texto": texto})


async def confirm(client, session, confirmation_id, confirmed=True):
    return await client.post(
        f"/sessoes/{session.id}/confirmacoes", json={"id": confirmation_id, "confirmado": confirmed}
    )


async def events_of(client, session):
    return (await client.get(f"/sessoes/{session.id}/eventos")).json()


async def request_hall(client, scripted, session, *, args=HALL, final=()):
    scripted.main.script(sc.transfer("reservas"))
    scripted.specialists.script(sc.tool_call("reservar_area", args), *final)
    r = await say(client, session, f"Reserve o salão de festas para {args['data']}.")
    return r.json()["confirmacoes_pendentes"][-1]["id"]


async def request_guest(client, scripted, session, *, final=()):
    scripted.main.script(sc.transfer("visitantes"))
    scripted.specialists.script(sc.tool_call("autorizar_visitante", GUEST), *final)
    r = await say(client, session, "Libere a Joana Ribeiro no dia 2030-04-21.")
    return r.json()["confirmacoes_pendentes"][-1]["id"]


async def request_test_tool(client, scripted, session):
    scripted.main.script(sc.transfer("reservas"))
    scripted.specialists.script(sc.tool_call("acao_com_confirmacao", {"descricao": "teste"}))
    r = await say(client, session, "Execute a ação de teste.")
    return r.json()["confirmacoes_pendentes"][-1]["id"]


async def visitors_of(engine, apartment="101"):
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT name, day::text FROM visitors WHERE apartment = :a"), {"a": apartment}
        )
        return [tuple(row) for row in result]


def results_of(events, tool):
    return [
        part["functionResponse"]["response"]
        for event in events
        for part in (event.get("content") or {}).get("parts", [])
        if part.get("functionResponse", {}).get("name") == tool
    ]


async def test_approval_returns_200_with_message_format(
    conversation_client, scripted, empty_session, engine
):
    p = await request_hall(
        conversation_client, scripted, empty_session, final=[sc.text("Reserva confirmada.")]
    )
    r = await confirm(conversation_client, empty_session, p)
    assert r.status_code == 200
    assert r.json() == {"resposta": "Reserva confirmada.", "confirmacoes_pendentes": []}
    assert len(await active(engine, apartment="101", area_id="salao-de-festas")) == 1


async def test_approval_after_other_messages(conversation_client, scripted, empty_session, engine):
    p = await request_hall(
        conversation_client, scripted, empty_session, final=[sc.text("Reserva confirmada.")]
    )
    scripted.main.script(sc.text("Olá! Como posso ajudar?"))
    await say(conversation_client, empty_session, "Olá")
    r = await confirm(conversation_client, empty_session, p)
    assert r.status_code == 200
    assert len(await active(engine, apartment="101", area_id="salao-de-festas")) == 1


async def test_approval_is_delivered_to_the_requesting_specialist(
    conversation_client, scripted, empty_session
):
    p = await request_hall(
        conversation_client, scripted, empty_session, final=[sc.text("Reserva confirmada.")]
    )
    await confirm(conversation_client, empty_session, p)
    events = await events_of(conversation_client, empty_session)
    answers = [
        e
        for e in events
        if e["author"] == "user"
        and any(
            part.get("functionResponse", {}).get("name") == "adk_request_confirmation"
            for part in (e.get("content") or {}).get("parts", [])
        )
    ]
    assert len(answers) == 1
    assert results_of(events, "reservar_area")[-1]["status"] == "reservada"
    assert events[-1]["author"] == "reservas"
    assert scripted.main.calls == 1


async def test_denial_returns_200_and_no_reservation(
    conversation_client, scripted, empty_session, engine
):
    p = await request_hall(conversation_client, scripted, empty_session, final=[sc.text(DENIED)])
    r = await confirm(conversation_client, empty_session, p, False)
    assert r.status_code == 200
    assert r.json() == {"resposta": DENIED, "confirmacoes_pendentes": []}
    assert await codes(engine) == SEED_CODES
    events = await events_of(conversation_client, empty_session)
    assert results_of(events, "reservar_area")[-1]["status"] == "nao_confirmada"


async def test_request_again_after_denial_and_approve(
    conversation_client, scripted, empty_session, engine
):
    p = await request_hall(conversation_client, scripted, empty_session, final=[sc.text(DENIED)])
    await confirm(conversation_client, empty_session, p, False)
    q = await request_hall(
        conversation_client, scripted, empty_session, final=[sc.text("Reserva confirmada.")]
    )
    assert q != p
    r = await confirm(conversation_client, empty_session, q)
    assert r.status_code == 200
    assert len(await active(engine, apartment="101", area_id="salao-de-festas")) == 1


async def test_visitor_approval_and_denial(conversation_client, scripted, empty_session, engine):
    p = await request_guest(
        conversation_client, scripted, empty_session, final=[sc.text("Autorizada.")]
    )
    r = await confirm(conversation_client, empty_session, p)
    assert r.status_code == 200 and r.json()["resposta"] == "Autorizada."
    assert await visitors_of(engine) == [("Joana Ribeiro", "2030-04-21")]
    events = await events_of(conversation_client, empty_session)
    assert results_of(events, "autorizar_visitante")[-1]["status"] == "autorizado"

    scripted.main.script(sc.transfer("visitantes"))
    other = {"nome": "Pedro Alves", "data": "2030-04-22"}
    scripted.specialists.script(
        sc.tool_call("autorizar_visitante", other), sc.text("Não autorizado.")
    )
    pending = (await say(conversation_client, empty_session, "Libere o Pedro.")).json()
    q = pending["confirmacoes_pendentes"][-1]["id"]
    r = await confirm(conversation_client, empty_session, q, False)
    assert r.status_code == 200
    assert await visitors_of(engine) == [("Joana Ribeiro", "2030-04-21")]


async def test_replay_of_approved_id_returns_409(
    conversation_client, scripted, empty_session, engine
):
    p = await request_hall(
        conversation_client, scripted, empty_session, final=[sc.text("Reserva confirmada.")]
    )
    await confirm(conversation_client, empty_session, p)
    before = await events_of(conversation_client, empty_session)
    r = await confirm(conversation_client, empty_session, p)
    assert r.status_code == 409
    assert r.json() == {"detail": NOT_PENDING_MESSAGE}
    assert len(await active(engine, apartment="101", area_id="salao-de-festas")) == 1
    assert await events_of(conversation_client, empty_session) == before


@pytest.mark.usefixtures("confirmation_tool_enabled")
async def test_replay_does_not_execute_test_tool_again(
    conversation_client, scripted, empty_session
):
    p = await request_test_tool(conversation_client, scripted, empty_session)
    scripted.specialists.script(sc.text("Ação executada."))
    r = await confirm(conversation_client, empty_session, p)
    assert r.status_code == 200 and r.json()["resposta"] == "Ação executada."
    assert (await confirm(conversation_client, empty_session, p)).status_code == 409
    assert scripted.confirmation.executions == ["teste"]


async def test_replay_after_denial_returns_409(
    conversation_client, scripted, empty_session, engine
):
    p = await request_hall(conversation_client, scripted, empty_session, final=[sc.text(DENIED)])
    await confirm(conversation_client, empty_session, p, False)
    r = await confirm(conversation_client, empty_session, p, True)
    assert r.status_code == 409
    assert await codes(engine) == SEED_CODES


async def test_unknown_id_returns_409(conversation_client, scripted, empty_session, engine):
    await request_hall(conversation_client, scripted, empty_session)
    before = await events_of(conversation_client, empty_session)
    calls = scripted.specialists.calls
    r = await confirm(conversation_client, empty_session, "id-inexistente")
    assert r.status_code == 409
    assert r.json() == {"detail": NOT_PENDING_MESSAGE}
    assert await codes(engine) == SEED_CODES
    assert await events_of(conversation_client, empty_session) == before
    assert scripted.specialists.calls == calls


async def test_id_from_another_session_returns_409(
    conversation_client, scripted, empty_session, session_201
):
    p = await request_hall(conversation_client, scripted, empty_session)
    r = await confirm(conversation_client, session_201, p)
    assert r.status_code == 409
    assert await events_of(conversation_client, session_201) == []


async def test_other_session_keeps_its_pending_item(
    conversation_client, scripted, session_with_pending, session_201
):
    r = await confirm(conversation_client, session_201, "adk-conf-reserva")
    assert r.status_code == 409
    assert len(await events_of(conversation_client, session_with_pending)) == 8


async def test_tool_call_id_returns_409(conversation_client, session_with_pending):
    r = await confirm(conversation_client, session_with_pending, "adk-fc-reserva")
    assert r.status_code == 409


async def test_chat_text_does_not_resolve(conversation_client, scripted, empty_session, engine):
    p = await request_hall(conversation_client, scripted, empty_session)
    scripted.main.script(sc.text("As confirmações são respondidas fora da conversa."))
    r = await say(conversation_client, empty_session, "Confirmo.")
    assert [i["id"] for i in r.json()["confirmacoes_pendentes"]] == [p]
    events = await events_of(conversation_client, empty_session)
    assert not any(
        part.get("functionResponse", {}).get("id") == p
        for e in events
        for part in (e.get("content") or {}).get("parts", [])
    )
    assert await codes(engine) == SEED_CODES


async def test_route_resolves_after_chat_text(conversation_client, scripted, empty_session, engine):
    p = await request_hall(
        conversation_client, scripted, empty_session, final=[sc.text("Reserva confirmada.")]
    )
    scripted.main.script(sc.text("As confirmações são respondidas fora da conversa."))
    await say(conversation_client, empty_session, "Confirmo.")
    r = await confirm(conversation_client, empty_session, p)
    assert r.status_code == 200
    assert len(await active(engine, apartment="101", area_id="salao-de-festas")) == 1


async def test_other_pending_items_are_listed(conversation_client, scripted, session_with_pending):
    scripted.specialists.script(sc.text("Joana Ribeiro autorizada."))
    r = await confirm(conversation_client, session_with_pending, "adk-conf-visita")
    assert r.status_code == 200
    assert [i["id"] for i in r.json()["confirmacoes_pendentes"]] == ["adk-conf-reserva"]


async def test_two_pending_of_same_specialist(conversation_client, scripted, empty_session, engine):
    p1 = await request_hall(conversation_client, scripted, empty_session)
    later = {"area": "salao-de-festas", "data": "2030-04-27"}
    p2 = await request_hall(
        conversation_client,
        scripted,
        empty_session,
        args=later,
        final=[sc.text("Reserva confirmada.")],
    )
    r = await confirm(conversation_client, empty_session, p2)
    assert [i["id"] for i in r.json()["confirmacoes_pendentes"]] == [p1]
    assert len(await active(engine, apartment="101", day="2030-04-27")) == 1
    assert await active(engine, apartment="101", day="2030-04-20") == []


RACE = {"area": "salao-de-festas", "data": "2030-05-11"}


async def _race_setup(client, scripted, session_101, session_201, final):
    p1 = await request_hall(client, scripted, session_101, args=RACE)
    p2 = await request_hall(client, scripted, session_201, args=RACE, final=final)
    return p1, p2


async def test_concurrent_approvals_one_winner(
    conversation_client, scripted, empty_session, session_201, engine
):
    p1, p2 = await _race_setup(
        conversation_client,
        scripted,
        empty_session,
        session_201,
        [sc.relay_tool_message, sc.relay_tool_message],
    )
    r1, r2 = await asyncio.gather(
        confirm(conversation_client, empty_session, p1),
        confirm(conversation_client, session_201, p2),
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert len(await active(engine, area_id="salao-de-festas", day="2030-05-11")) == 1
    texts = {r1.json()["resposta"], r2.json()["resposta"]}
    assert "Essa data não está mais disponível." in texts
    statuses = set()
    for session in (empty_session, session_201):
        events = await events_of(conversation_client, session)
        statuses.add(results_of(events, "reservar_area")[-1]["status"])
    assert statuses == {"reservada", "data_indisponivel"}


async def test_concurrent_approvals_with_model_failure(
    conversation_client, scripted, empty_session, session_201, engine
):
    p1, p2 = await _race_setup(
        conversation_client,
        scripted,
        empty_session,
        session_201,
        [sc.quota_error(), sc.quota_error()],
    )
    r1, r2 = await asyncio.gather(
        confirm(conversation_client, empty_session, p1),
        confirm(conversation_client, session_201, p2),
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert len(await active(engine, area_id="salao-de-festas", day="2030-05-11")) == 1
    assert {r1.json()["resposta"], r2.json()["resposta"]} == {
        APPROVED_MESSAGE,
        "Essa data não está mais disponível.",
    }
    assert r1.json()["confirmacoes_pendentes"] == [] == r2.json()["confirmacoes_pendentes"]


async def test_lost_race_is_a_normal_refusal(
    conversation_client, scripted, empty_session, session_201, engine
):
    p1, p2 = await _race_setup(
        conversation_client,
        scripted,
        empty_session,
        session_201,
        [sc.text("Reserva confirmada."), sc.text("Essa data não está mais disponível.")],
    )
    await confirm(conversation_client, session_201, p2)
    winner = (await active(engine, apartment="201", area_id="salao-de-festas"))[0][0]
    r = await confirm(conversation_client, empty_session, p1)
    assert r.status_code == 200
    assert r.json() == {
        "resposta": "Essa data não está mais disponível.",
        "confirmacoes_pendentes": [],
    }
    assert await active(engine, apartment="101", day="2030-05-11") == []
    events = await events_of(conversation_client, empty_session)
    assert set(results_of(events, "reservar_area")[-1]) == {"status", "mensagem"}
    assert winner not in json.dumps(events) and winner not in r.text


async def test_approval_after_app_restart(
    conversation_client, restarted_client, scripted, empty_session, engine
):
    p = await request_hall(conversation_client, scripted, empty_session)
    restarted_client.scripted.specialists.script(sc.text("Reserva confirmada."))
    r = await confirm(restarted_client, empty_session, p)
    assert r.status_code == 200 and r.json()["resposta"] == "Reserva confirmada."
    assert len(await active(engine, apartment="101", area_id="salao-de-festas")) == 1


async def test_replay_after_app_restart_returns_409(
    conversation_client, restarted_client, scripted, empty_session, engine
):
    p = await request_hall(
        conversation_client, scripted, empty_session, final=[sc.text("Reserva confirmada.")]
    )
    await confirm(conversation_client, empty_session, p)
    r = await confirm(restarted_client, empty_session, p)
    assert r.status_code == 409
    assert len(await active(engine, apartment="101", area_id="salao-de-festas")) == 1


@pytest.mark.parametrize(
    "body",
    [
        {"confirmado": True},
        {"id": "", "confirmado": True},
        {"id": "   ", "confirmado": True},
        {"id": 123, "confirmado": True},
        {"id": "adk-conf-reserva"},
        {"id": "adk-conf-reserva", "confirmado": "sim"},
        {"id": "adk-conf-reserva", "confirmado": "true"},
        {"id": "adk-conf-reserva", "confirmado": 1},
        {"id": "adk-conf-reserva", "confirmado": None},
    ],
)
async def test_missing_or_invalid_fields_return_422(
    conversation_client, session_with_pending, body
):
    r = await conversation_client.post(
        f"/sessoes/{session_with_pending.id}/confirmacoes", json=body
    )
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str)
    assert len(await events_of(conversation_client, session_with_pending)) == 8


async def test_invalid_json_returns_422(conversation_client, session_with_pending):
    r = await conversation_client.post(
        f"/sessoes/{session_with_pending.id}/confirmacoes",
        content='{"id": ',
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str)


async def test_extra_fields_are_ignored(conversation_client, scripted, session_with_pending):
    scripted.specialists.script(sc.text("Autorização negada."))
    body = {"id": "adk-conf-visita", "confirmado": False, "apartamento": "302"}
    r = await conversation_client.post(
        f"/sessoes/{session_with_pending.id}/confirmacoes", json=body
    )
    assert r.status_code == 200
    from aurora.sessions.service import find_session, session_apartment

    current = await find_session(
        conversation_client.app.state.session_service, session_id=session_with_pending.id
    )
    assert session_apartment(current) == "101"


async def test_item_still_answerable_after_422(conversation_client, scripted, session_with_pending):
    bad = await conversation_client.post(
        f"/sessoes/{session_with_pending.id}/confirmacoes",
        json={"id": "adk-conf-reserva", "confirmado": "sim"},
    )
    assert bad.status_code == 422
    scripted.specialists.script(sc.text(DENIED))
    r = await confirm(conversation_client, session_with_pending, "adk-conf-reserva", False)
    assert r.status_code == 200


async def test_unknown_session_returns_404(conversation_client):
    ok = await conversation_client.post(
        "/sessoes/sessao-inexistente/confirmacoes", json={"id": "x", "confirmado": True}
    )
    bad = await conversation_client.post(
        "/sessoes/sessao-inexistente/confirmacoes", json={"confirmado": "sim"}
    )
    assert ok.status_code == 404 and bad.status_code == 404


@pytest.mark.usefixtures("confirmation_tool_enabled")
async def test_failed_resume_returns_200_and_keeps_item(
    conversation_client, scripted, empty_session
):
    p = await request_test_tool(conversation_client, scripted, empty_session)
    scripted.confirmation.fail_next = True
    r = await confirm(conversation_client, empty_session, p)
    assert r.status_code == 200
    body = r.json()
    assert body["resposta"] == NOT_EXECUTED_MESSAGE
    assert [i["id"] for i in body["confirmacoes_pendentes"]] == [p]
    assert scripted.confirmation.executions == []


@pytest.mark.usefixtures("confirmation_tool_enabled")
async def test_answer_again_after_failed_resume(conversation_client, scripted, empty_session):
    p = await request_test_tool(conversation_client, scripted, empty_session)
    scripted.confirmation.fail_next = True
    await confirm(conversation_client, empty_session, p)
    scripted.specialists.script(sc.text("Ação executada."))
    r = await confirm(conversation_client, empty_session, p)
    assert r.status_code == 200
    assert r.json() == {"resposta": "Ação executada.", "confirmacoes_pendentes": []}
    assert scripted.confirmation.executions == ["teste"]


async def test_model_failure_after_tool_returns_200(
    conversation_client, scripted, empty_session, engine
):
    p = await request_hall(conversation_client, scripted, empty_session, final=[sc.quota_error()])
    r = await confirm(conversation_client, empty_session, p)
    assert r.status_code == 200
    assert r.json() == {"resposta": APPROVED_MESSAGE, "confirmacoes_pendentes": []}
    assert len(await active(engine, apartment="101", area_id="salao-de-festas")) == 1
    assert (await confirm(conversation_client, empty_session, p)).status_code == 409


async def test_empty_model_text_uses_fixed_text(conversation_client, scripted, empty_session):
    p = await request_hall(conversation_client, scripted, empty_session, final=[sc.empty_text()])
    r = await confirm(conversation_client, empty_session, p)
    assert r.json()["resposta"] == APPROVED_MESSAGE


async def test_message_route_still_works_after_confirmation(
    conversation_client, scripted, empty_session
):
    p = await request_hall(
        conversation_client,
        scripted,
        empty_session,
        final=[sc.quota_error()],
    )
    await confirm(conversation_client, empty_session, p)
    scripted.main.script(sc.text("Olá! Como posso ajudar?"))
    r = await say(conversation_client, empty_session, "Olá")
    assert r.status_code == 200
    assert r.json() == {"resposta": "Olá! Como posso ajudar?", "confirmacoes_pendentes": []}


async def test_session_store_failure_returns_503(conversation_client, session_with_pending):
    from aurora.sessions.service import SessionStoreError

    async def broken(*args, **kwargs):
        raise SessionStoreError()

    service = conversation_client.app.state.session_service
    original = service.get_session
    calls = {"n": 0}

    async def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] > 1:
            return await broken()
        return await original(*args, **kwargs)

    service.get_session = flaky
    try:
        r = await confirm(conversation_client, session_with_pending, "adk-conf-reserva")
    finally:
        service.get_session = original
    assert r.status_code == 503
    assert "aurora" not in r.json()["detail"].lower().replace("serviço", "")
    assert "SELECT" not in r.text
