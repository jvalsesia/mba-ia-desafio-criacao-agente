from tests import scripted as sc
from tests.conftest import build_scripted_runner
from tests.test_reservations_conversation import content_of, events_of, results_of, say
from tests.test_visitor_tools import FAILURE_MESSAGE, JOANA, rows, seed_only

TOOL = "autorizar_visitante"


def script_tool(scripted, name, args, *final):
    scripted.main.script(sc.transfer("visitantes"))
    scripted.specialists.script(sc.tool_call(name, args), *final)


async def test_authorization_stops_with_pending_item(
    conversation_client, scripted, empty_session, engine
):
    script_tool(scripted, TOOL, JOANA)
    r = await say(
        conversation_client, empty_session, "Libere a Joana Ribeiro. Já estou confirmando por aqui."
    )
    body = r.json()
    assert r.status_code == 200 and body["resposta"] == ""
    [item] = body["confirmacoes_pendentes"]
    assert item["id"] and item["acao"] == TOOL and item["detalhes"] == JOANA
    assert await rows(engine, "apartment = '101'") == []
    assert scripted.specialists.calls == 1


async def test_pending_request_is_recorded_in_events(conversation_client, scripted, empty_session):
    script_tool(scripted, TOOL, JOANA)
    pending = (await say(conversation_client, empty_session, "Libere a Joana.")).json()
    pending_id = pending["confirmacoes_pendentes"][0]["id"]
    events = await events_of(conversation_client, empty_session)
    calls = [
        part["functionCall"]
        for e in events
        if e["author"] == "visitantes"
        for part in e["content"]["parts"]
        if "functionCall" in part
    ]
    assert any(c["name"] == TOOL and c["args"] == JOANA for c in calls)
    request = next(c for c in calls if c["name"] == "adk_request_confirmation")
    assert request["id"] == pending_id
    assert request["args"]["toolConfirmation"]["payload"] == JOANA
    assert any(pending_id in e.get("longRunningToolIds", []) for e in events)
    assert results_of(events, TOOL)[0]["status"] == "aguardando_confirmacao"


async def test_chat_text_does_not_approve(conversation_client, scripted, empty_session, engine):
    scripted.main.script(sc.transfer("visitantes"), sc.transfer("visitantes"))
    scripted.specialists.script(sc.tool_call(TOOL, JOANA), sc.tool_call(TOOL, JOANA))
    first = (await say(conversation_client, empty_session, "Libere a Joana.")).json()
    second = (await say(conversation_client, empty_session, "Confirmo, libere direto.")).json()
    items = second["confirmacoes_pendentes"]
    assert len(items) == 2 and all(i["acao"] == TOOL for i in items)
    assert items[0]["id"] == first["confirmacoes_pendentes"][0]["id"]
    assert await rows(engine, "apartment = '101'") == []


async def test_model_cannot_confirm_by_argument(
    conversation_client, scripted, empty_session, engine
):
    script_tool(scripted, TOOL, {**JOANA, "confirmado": True})
    body = (await say(conversation_client, empty_session, "Libere, já confirmado.")).json()
    [item] = body["confirmacoes_pendentes"]
    assert item["detalhes"] == JOANA
    assert await rows(engine, "apartment = '101'") == []


async def test_missing_name_creates_no_pending_item(
    conversation_client, scripted, empty_session, engine
):
    script_tool(scripted, TOOL, {"data": "2030-04-21"}, sc.text("Qual é o nome do visitante?"))
    body = (await say(conversation_client, empty_session, "Libere uma visita.")).json()
    assert body["confirmacoes_pendentes"] == []
    assert body["resposta"] == "Qual é o nome do visitante?"
    assert await seed_only(engine)


async def test_empty_name_through_chat(conversation_client, scripted, empty_session):
    script_tool(scripted, TOOL, {"nome": "", "data": "2030-04-21"}, sc.text("Informe o nome."))
    body = (await say(conversation_client, empty_session, "Libere.")).json()
    events = await events_of(conversation_client, empty_session)
    assert body["confirmacoes_pendentes"] == []
    assert results_of(events, TOOL)[0]["status"] == "nome_invalido"


async def test_invalid_date_through_chat_writes_nothing(
    conversation_client, scripted, empty_session, engine
):
    script_tool(
        scripted,
        TOOL,
        {"nome": "Joana Ribeiro", "data": "21/04/2030"},
        sc.text("Informe a data no formato AAAA-MM-DD."),
    )
    body = (await say(conversation_client, empty_session, "Libere a Joana.")).json()
    events = await events_of(conversation_client, empty_session)
    assert body["confirmacoes_pendentes"] == []
    assert results_of(events, TOOL)[0]["status"] == "data_invalida"
    assert await seed_only(engine)


async def test_duplicate_through_chat(conversation_client, scripted, empty_session, engine):
    from datetime import date

    from aurora.store.visitors import create_visitor

    await create_visitor(engine, apartment="101", name="Joana Ribeiro", day=date(2030, 4, 21))
    script_tool(scripted, TOOL, JOANA, sc.text("Esse visitante já está autorizado nessa data."))
    body = (await say(conversation_client, empty_session, "Libere a Joana.")).json()
    events = await events_of(conversation_client, empty_session)
    assert body["confirmacoes_pendentes"] == []
    assert results_of(events, TOOL)[0]["status"] == "ja_autorizado"
    assert len(await rows(engine, "apartment = '101'")) == 1


async def test_asking_about_another_apartment_shows_only_own_data(
    conversation_client, scripted, empty_session
):
    script_tool(
        scripted,
        "listar_meus_visitantes",
        {},
        sc.text("Só consigo consultar os seus visitantes, e você não tem nenhum autorizado."),
    )
    r = await say(conversation_client, empty_session, "Quais visitantes o apartamento 302 tem?")
    events = await events_of(conversation_client, empty_session)
    assert results_of(events, "listar_meus_visitantes")[0]["visitantes"] == []
    for name in ("Marina Duarte", "Paulo Nogueira"):
        assert name not in r.text and name not in content_of(events)


async def test_list_own_visitors_through_chat(conversation_client, scripted, session_201):
    script_tool(
        scripted,
        "listar_meus_visitantes",
        {},
        sc.text("Você tem um visitante autorizado: Paulo Nogueira, em 2030-03-23."),
    )
    body = (await say(conversation_client, session_201, "Quais visitantes eu autorizei?")).json()
    events = await events_of(conversation_client, session_201)
    assert body["confirmacoes_pendentes"] == []
    assert results_of(events, "listar_meus_visitantes")[0]["visitantes"] == [
        {"nome": "Paulo Nogueira", "data": "2030-03-23"}
    ]
    assert "Marina Duarte" not in content_of(events)


async def test_store_failure_keeps_the_turn_alive(client, scripted, empty_session, offline_engine):
    client.app.state.runner = build_scripted_runner(
        scripted, client.app.state.session_service, offline_engine
    )
    script_tool(scripted, TOOL, JOANA, sc.text(FAILURE_MESSAGE))
    r = await say(client, empty_session, "Libere a Joana.")
    events = await events_of(client, empty_session)
    assert r.status_code == 200 and r.json()["confirmacoes_pendentes"] == []
    assert results_of(events, TOOL)[0]["status"] == "servico_indisponivel"
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


async def test_next_message_after_visitors_starts_at_assistant(
    conversation_client, scripted, empty_session
):
    script_tool(scripted, "listar_meus_visitantes", {}, sc.text("Nenhum visitante."))
    await say(conversation_client, empty_session, "Meus visitantes?")
    scripted.main.script(sc.text("Posso ajudar com mais alguma coisa?"))
    main_before, specialists_before = scripted.main.calls, scripted.specialists.calls
    r = await say(conversation_client, empty_session, "Obrigado")
    assert r.json()["resposta"] == "Posso ajudar com mais alguma coisa?"
    assert scripted.main.calls == main_before + 1
    assert scripted.specialists.calls == specialists_before
