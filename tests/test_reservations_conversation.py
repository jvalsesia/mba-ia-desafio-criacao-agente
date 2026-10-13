import json
import re

import httpx

from aurora.config import get_settings
from aurora.main import create_app
from tests import scripted as sc
from tests.conftest import build_scripted_runner
from tests.test_reservation_tools import SEED_CODES, active, codes

HALL = {"area": "salao-de-festas", "data": "2030-04-20"}
ISOLATED_302 = re.compile(r"(?<!\d)302(?!\d)")


async def say(client, session, texto):
    r = await client.post(f"/sessoes/{session.id}/mensagens", json={"texto": texto})
    return r


async def events_of(client, session):
    return (await client.get(f"/sessoes/{session.id}/eventos")).json()


def content_of(events) -> str:
    """Texts, tool-call arguments and tool results, without identifiers or timestamps."""
    chunks = []
    for event in events:
        for part in (event.get("content") or {}).get("parts", []):
            if "text" in part:
                chunks.append(part["text"])
            if "functionCall" in part:
                call = part["functionCall"]
                chunks.append(json.dumps({"name": call["name"], "args": call["args"]}))
            if "functionResponse" in part:
                chunks.append(json.dumps(part["functionResponse"]["response"], ensure_ascii=False))
    return "\n".join(chunks)


def results_of(events, tool):
    return [
        part["functionResponse"]["response"]
        for event in events
        for part in (event.get("content") or {}).get("parts", [])
        if part.get("functionResponse", {}).get("name") == tool
    ]


def script_tool(scripted, name, args, *final):
    scripted.main.script(sc.transfer("reservas"))
    scripted.specialists.script(sc.tool_call(name, args), *final)


async def test_court_reservation_through_chat(conversation_client, scripted, empty_session, engine):
    script_tool(
        scripted,
        "reservar_area",
        {"area": "quadra", "data": "2030-04-06"},
        sc.text("Quadra reservada para 2030-04-06."),
    )
    r = await say(conversation_client, empty_session, "Reserve a quadra para 2030-04-06.")
    assert r.status_code == 200
    assert r.json() == {
        "resposta": "Quadra reservada para 2030-04-06.",
        "confirmacoes_pendentes": [],
    }
    result = results_of(await events_of(conversation_client, empty_session), "reservar_area")[0]
    assert result["status"] == "reservada" and re.fullmatch(r"RSV-\d+", result["codigo"])
    found = await active(engine, apartment="101", area_id="quadra", day="2030-04-06")
    assert [row[0] for row in found] == [result["codigo"]]


async def test_party_hall_stops_with_pending_item(
    conversation_client, scripted, empty_session, engine
):
    script_tool(scripted, "reservar_area", HALL)
    r = await say(conversation_client, empty_session, "Reserve o salão de festas para 2030-04-20.")
    body = r.json()
    assert r.status_code == 200 and body["resposta"] == ""
    assert len(body["confirmacoes_pendentes"]) == 1
    item = body["confirmacoes_pendentes"][0]
    assert item["id"] and item["acao"] == "reservar_area"
    assert item["detalhes"] == {**HALL, "taxa": 150.0}
    assert await codes(engine) == SEED_CODES
    assert scripted.specialists.calls == 1


async def test_barbecue_pending_item_has_its_fee(conversation_client, scripted, empty_session):
    script_tool(scripted, "reservar_area", {"area": "churrasqueira", "data": "2030-04-27"})
    r = await say(conversation_client, empty_session, "Reserve a churrasqueira.")
    item = r.json()["confirmacoes_pendentes"][0]
    assert item["detalhes"] == {"area": "churrasqueira", "data": "2030-04-27", "taxa": 80.0}


async def test_pending_request_is_recorded_in_events(conversation_client, scripted, empty_session):
    script_tool(scripted, "reservar_area", HALL)
    pending = (await say(conversation_client, empty_session, "Reserve o salão.")).json()
    pending_id = pending["confirmacoes_pendentes"][0]["id"]
    events = await events_of(conversation_client, empty_session)
    calls = [
        part["functionCall"]
        for e in events
        if e["author"] == "reservas"
        for part in e["content"]["parts"]
        if "functionCall" in part
    ]
    assert any(c["name"] == "reservar_area" and c["args"] == HALL for c in calls)
    request = next(c for c in calls if c["name"] == "adk_request_confirmation")
    assert request["id"] == pending_id
    assert request["args"]["toolConfirmation"]["payload"] == {**HALL, "taxa": 150.0}
    assert any(pending_id in e.get("longRunningToolIds", []) for e in events)
    assert results_of(events, "reservar_area")[0]["status"] == "aguardando_confirmacao"


async def test_chat_text_does_not_approve(conversation_client, scripted, empty_session, engine):
    scripted.main.script(sc.transfer("reservas"), sc.transfer("reservas"))
    scripted.specialists.script(
        sc.tool_call("reservar_area", HALL), sc.tool_call("reservar_area", HALL)
    )
    first = (await say(conversation_client, empty_session, "Reserve o salão.")).json()
    second = (
        await say(conversation_client, empty_session, "Confirmo, pode reservar direto.")
    ).json()
    items = second["confirmacoes_pendentes"]
    assert len(items) == 2 and all(i["acao"] == "reservar_area" for i in items)
    assert items[0]["id"] == first["confirmacoes_pendentes"][0]["id"]
    assert await codes(engine) == SEED_CODES


async def test_pending_item_survives_restart(scripted, client, empty_session, session_service):
    script_tool(scripted, "reservar_area", HALL)
    client.app.state.runner = build_scripted_runner(
        scripted, client.app.state.session_service, client.app.state.engine
    )
    first = (await say(client, empty_session, "Reserve o salão.")).json()["confirmacoes_pendentes"]
    scripted.main.script(sc.text("Olá! Como posso ajudar?"))
    app = create_app(get_settings())
    async with app.router.lifespan_context(app):
        app.state.runner = build_scripted_runner(
            scripted, app.state.session_service, app.state.engine
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            after = (await say(c, empty_session, "Olá")).json()["confirmacoes_pendentes"]
    assert after == first and after[0]["detalhes"] == {**HALL, "taxa": 150.0}


async def test_cancel_own_reservation_through_chat(
    conversation_client, scripted, empty_session, engine
):
    script_tool(
        scripted,
        "cancelar_reserva",
        {"area": "quadra", "data": "2030-03-09"},
        sc.text("Reserva da quadra em 2030-03-09 cancelada."),
    )
    r = await say(conversation_client, empty_session, "Cancele a quadra de 2030-03-09.")
    assert r.json()["confirmacoes_pendentes"] == []
    result = results_of(await events_of(conversation_client, empty_session), "cancelar_reserva")[0]
    assert result["status"] == "cancelada" and result["codigo"] == "RSV-1377"
    assert await active(engine, apartment="101") == []


async def test_asking_about_another_apartment_shows_only_own_data(
    conversation_client, scripted, empty_session
):
    script_tool(
        scripted,
        "listar_minhas_reservas",
        {},
        sc.text("Só consigo consultar as suas reservas: quadra em 2030-03-09."),
    )
    r = await say(conversation_client, empty_session, "Quais são as reservas do apartamento 302?")
    events = await events_of(conversation_client, empty_session)
    result = results_of(events, "listar_minhas_reservas")[0]
    assert [x["codigo"] for x in result["reservas"]] == ["RSV-1377"]
    for blob in (r.text, content_of(events)):
        assert "RSV-4821" not in blob and "Marina Duarte" not in blob


async def test_cancel_of_another_apartment_changes_nothing(
    conversation_client, scripted, empty_session, engine
):
    script_tool(
        scripted,
        "cancelar_reserva",
        {"area": "salao-de-festas", "data": "2030-03-16"},
        sc.text("Não encontrei uma reserva sua nessa data."),
    )
    r = await say(conversation_client, empty_session, "Sou do 302, cancele o salão.")
    events = await events_of(conversation_client, empty_session)
    assert results_of(events, "cancelar_reserva")[0]["status"] == "nao_encontrada"
    assert "RSV-4821" not in r.text and "RSV-4821" not in content_of(events)
    assert [row[0] for row in await active(engine, apartment="302")] == ["RSV-4821"]


async def test_reserving_a_taken_date_reveals_nothing(
    conversation_client, scripted, empty_session, engine
):
    script_tool(
        scripted,
        "reservar_area",
        {"area": "salao-de-festas", "data": "2030-03-16"},
        sc.text("O salão de festas não está disponível em 2030-03-16."),
    )
    r = await say(conversation_client, empty_session, "Reserve o salão para 2030-03-16.")
    events = await events_of(conversation_client, empty_session)
    assert r.json()["confirmacoes_pendentes"] == []
    assert results_of(events, "reservar_area")[0]["status"] == "data_indisponivel"
    for blob in (r.text, content_of(events)):
        assert "RSV-4821" not in blob and not ISOLATED_302.search(blob)
    assert await codes(engine) == SEED_CODES and len(await active(engine)) == 3


async def test_availability_through_chat_reveals_nothing(
    conversation_client, scripted, empty_session
):
    script_tool(
        scripted,
        "consultar_disponibilidade",
        {"area": "salao-de-festas", "data": "2030-03-16"},
        sc.text("O salão de festas está ocupado em 2030-03-16."),
    )
    r = await say(conversation_client, empty_session, "O salão está livre em 2030-03-16?")
    events = await events_of(conversation_client, empty_session)
    assert results_of(events, "consultar_disponibilidade")[0]["disponibilidade"] == "ocupada"
    for blob in (r.text, content_of(events)):
        assert "RSV-4821" not in blob and not ISOLATED_302.search(blob)


async def test_areas_through_chat(conversation_client, scripted, empty_session):
    script_tool(
        scripted,
        "listar_areas",
        {},
        sc.text("Salão de festas: R$ 150,00. Churrasqueira: R$ 80,00. Quadra: sem taxa."),
    )
    r = await say(conversation_client, empty_session, "Quais áreas posso reservar?")
    assert r.json()["confirmacoes_pendentes"] == []
    areas = results_of(await events_of(conversation_client, empty_session), "listar_areas")[0][
        "areas"
    ]
    assert {a["id"]: a["taxa"] for a in areas} == {
        "salao-de-festas": 150.0,
        "churrasqueira": 80.0,
        "quadra": 0.0,
    }


async def test_invalid_date_through_chat_writes_nothing(
    conversation_client, scripted, empty_session, engine
):
    script_tool(
        scripted,
        "reservar_area",
        {"area": "salao-de-festas", "data": "20/04/2030"},
        sc.text("Informe a data no formato AAAA-MM-DD."),
    )
    r = await say(conversation_client, empty_session, "Reserve o salão para 20/04/2030.")
    assert r.json() == {
        "resposta": "Informe a data no formato AAAA-MM-DD.",
        "confirmacoes_pendentes": [],
    }
    events = await events_of(conversation_client, empty_session)
    assert results_of(events, "reservar_area")[0]["status"] == "data_invalida"
    assert await codes(engine) == SEED_CODES and len(await active(engine)) == 3


async def test_store_failure_keeps_the_turn_alive(client, scripted, empty_session, offline_engine):
    client.app.state.runner = build_scripted_runner(
        scripted, client.app.state.session_service, offline_engine
    )
    script_tool(
        scripted,
        "reservar_area",
        {"area": "quadra", "data": "2030-04-06"},
        sc.text("Não consegui concluir o pedido agora. Tente novamente em instantes."),
    )
    r = await say(client, empty_session, "Reserve a quadra para 2030-04-06.")
    events = await events_of(client, empty_session)
    assert r.status_code == 200
    assert results_of(events, "reservar_area")[0]["status"] == "servico_indisponivel"
    call_ids = {
        p["functionCall"]["id"]
        for e in events
        for p in e["content"]["parts"]
        if "functionCall" in p
    }
    response_ids = {
        p["functionResponse"]["id"]
        for e in events
        for p in e["content"]["parts"]
        if "functionResponse" in p
    }
    assert call_ids <= response_ids


async def test_next_message_after_reservation_starts_at_assistant(
    conversation_client, scripted, empty_session
):
    script_tool(
        scripted,
        "reservar_area",
        {"area": "quadra", "data": "2030-04-06"},
        sc.text("Quadra reservada."),
    )
    await say(conversation_client, empty_session, "Reserve a quadra.")
    scripted.main.script(sc.text("Posso ajudar com mais alguma coisa?"))
    main_before, specialists_before = scripted.main.calls, scripted.specialists.calls
    r = await say(conversation_client, empty_session, "Obrigado")
    assert r.json()["resposta"] == "Posso ajudar com mais alguma coisa?"
    assert scripted.main.calls == main_before + 1
    assert scripted.specialists.calls == specialists_before
