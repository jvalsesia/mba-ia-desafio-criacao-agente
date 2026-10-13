import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from aurora.config import get_settings
from aurora.conversation.service import (
    APOLOGY_MESSAGE,
    ASSISTANT_UNAVAILABLE_MESSAGE,
    NO_REPLY_MESSAGE,
)
from aurora.main import create_app
from tests import scripted as sc
from tests.conftest import build_scripted_runner

PENDING_IDS = ["adk-conf-reserva", "adk-conf-visita"]


async def post(client, session, body):
    return await client.post(f"/sessoes/{session.id}/mensagens", json=body)


async def events_of(client, session):
    return (await client.get(f"/sessoes/{session.id}/eventos")).json()


async def test_message_returns_200_with_reply_and_empty_pending(
    conversation_client, scripted, empty_session
):
    scripted.main.script(sc.text("Olá! Sou o assistente do Residencial Aurora."))
    r = await post(conversation_client, empty_session, {"texto": "Olá"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == {
        "resposta": "Olá! Sou o assistente do Residencial Aurora.",
        "confirmacoes_pendentes": [],
    }


async def test_message_is_recorded_in_session_events(conversation_client, scripted, empty_session):
    scripted.main.script(sc.text("Oi."))
    await post(conversation_client, empty_session, {"texto": "Olá"})
    events = await events_of(conversation_client, empty_session)
    assert [e["author"] for e in events] == ["user", "assistente"]
    assert events[0]["content"]["parts"][0]["text"] == "Olá"


async def test_message_text_is_trimmed(conversation_client, scripted, empty_session):
    scripted.main.script(sc.text("Oi."))
    r = await post(conversation_client, empty_session, {"texto": "  Olá  "})
    assert r.status_code == 200
    events = await events_of(conversation_client, empty_session)
    assert events[0]["content"]["parts"][0]["text"] == "Olá"


async def test_message_accepts_2000_characters(conversation_client, scripted, empty_session):
    scripted.main.script(sc.text("Oi."))
    r = await post(conversation_client, empty_session, {"texto": "a" * 2000})
    assert r.status_code == 200
    assert scripted.main.calls == 1


async def test_message_ignores_extra_fields(conversation_client, scripted, empty_session):
    scripted.main.script(sc.text("Oi."))
    r = await post(conversation_client, empty_session, {"texto": "Olá", "apartamento": "302"})
    assert r.status_code == 200
    from aurora.sessions.service import find_session, session_apartment

    reread = await find_session(
        conversation_client.app.state.session_service, session_id=empty_session.id
    )
    assert session_apartment(reread) == "101"


async def test_routing_to_specialist_and_back(conversation_client, scripted, empty_session):
    scripted.main.script(sc.transfer("reservas"), sc.text("Posso ajudar."))
    scripted.specialists.script(sc.text("Ainda não consigo consultar reservas."))
    r = await post(conversation_client, empty_session, {"texto": "Minhas reservas?"})
    assert r.json()["resposta"] == "Ainda não consigo consultar reservas."
    events = await events_of(conversation_client, empty_session)
    assert events[-1]["author"] == "reservas"
    r = await post(conversation_client, empty_session, {"texto": "O que você faz?"})
    assert r.json()["resposta"] == "Posso ajudar."
    assert scripted.specialists.calls == 1


async def test_routing_to_visitors(conversation_client, scripted, empty_session):
    scripted.main.script(sc.transfer("visitantes"))
    scripted.specialists.script(sc.text("Ainda não consigo consultar visitantes."))
    r = await post(conversation_client, empty_session, {"texto": "Visitantes?"})
    assert r.json()["resposta"] == "Ainda não consigo consultar visitantes."
    assert (await events_of(conversation_client, empty_session))[-1]["author"] == "visitantes"


async def test_message_lists_pending_items(conversation_client, scripted, session_with_pending):
    scripted.main.script(sc.text("Olá! Como posso ajudar?"))
    r = await post(conversation_client, session_with_pending, {"texto": "Olá"})
    assert r.json()["confirmacoes_pendentes"] == [
        {
            "id": "adk-conf-reserva",
            "acao": "reservar_area",
            "detalhes": {"area": "salao-de-festas", "data": "2030-04-20", "taxa": 150.0},
        },
        {
            "id": "adk-conf-visita",
            "acao": "autorizar_visitante",
            "detalhes": {"nome": "Joana Ribeiro", "data": "2030-04-21"},
        },
    ]


async def test_pending_persist_across_messages(conversation_client, scripted, session_with_pending):
    scripted.main.script(sc.text("Um."), sc.text("Dois."))
    await post(conversation_client, session_with_pending, {"texto": "Olá"})
    r = await post(conversation_client, session_with_pending, {"texto": "Confirmo, pode executar."})
    assert [i["id"] for i in r.json()["confirmacoes_pendentes"]] == PENDING_IDS


async def test_message_does_not_list_answered(conversation_client, scripted, session_with_answered):
    scripted.main.script(sc.text("Oi."))
    r = await post(conversation_client, session_with_answered, {"texto": "Olá"})
    assert [i["id"] for i in r.json()["confirmacoes_pendentes"]] == ["adk-conf-visita"]


@pytest.mark.usefixtures("confirmation_tool_enabled")
async def test_paused_run_and_second_message(conversation_client, scripted, empty_session):
    scripted.main.script(sc.transfer("reservas"), sc.text("Olá! Como posso ajudar?"))
    scripted.specialists.script(sc.tool_call("acao_com_confirmacao", {"descricao": "teste"}))
    r = await post(conversation_client, empty_session, {"texto": "Execute a ação de teste."})
    body = r.json()
    assert body["resposta"] == ""
    assert len(body["confirmacoes_pendentes"]) == 1
    item = body["confirmacoes_pendentes"][0]
    assert item["id"] and item["acao"] == "acao_com_confirmacao"
    assert item["detalhes"] == {"descricao": "teste"}
    r = await post(conversation_client, empty_session, {"texto": "Olá"})
    assert r.json()["resposta"] == "Olá! Como posso ajudar?"
    assert [i["id"] for i in r.json()["confirmacoes_pendentes"]] == [item["id"]]
    assert scripted.confirmation.executions == []


@pytest.mark.parametrize(
    "body",
    [{"texto": ""}, {"texto": "   "}, {"texto": "a" * 2001}],
)
async def test_invalid_text_returns_422_without_model_call(
    body, conversation_client, scripted, empty_session
):
    scripted.main.script(sc.text("Olá!"))
    r = await post(conversation_client, empty_session, body)
    assert r.status_code == 422
    assert "texto" in r.json()["detail"]
    assert scripted.main.calls == 0
    assert await events_of(conversation_client, empty_session) == []


async def test_missing_text_returns_422(conversation_client, empty_session):
    r = await post(conversation_client, empty_session, {})
    assert r.status_code == 422 and "texto" in r.json()["detail"]


async def test_non_string_text_returns_422(conversation_client, empty_session):
    r = await post(conversation_client, empty_session, {"texto": 123})
    assert r.status_code == 422 and r.json()["detail"]


async def test_malformed_json_returns_422(conversation_client, empty_session):
    r = await conversation_client.post(
        f"/sessoes/{empty_session.id}/mensagens",
        content='{"texto": ',
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 422 and r.json()["detail"]


async def test_unknown_session_returns_404_without_model_call(conversation_client, scripted):
    r = await conversation_client.post(
        "/sessoes/sessao-inexistente/mensagens", json={"texto": "Olá"}
    )
    assert r.status_code == 404 and r.json()["detail"]
    assert scripted.main.calls == 0


async def test_unknown_session_with_invalid_body_returns_404(conversation_client):
    r = await conversation_client.post("/sessoes/sessao-inexistente/mensagens", json={"texto": ""})
    assert r.status_code == 404


async def test_gemini_failure_returns_503(conversation_client, scripted, empty_session):
    scripted.main.script(sc.quota_error(), sc.text("Olá! Como posso ajudar?"))
    r = await post(conversation_client, empty_session, {"texto": "Olá"})
    assert r.status_code == 503
    assert r.json() == {"detail": ASSISTANT_UNAVAILABLE_MESSAGE}
    r = await post(conversation_client, empty_session, {"texto": "Olá de novo"})
    assert r.status_code == 200 and r.json()["resposta"] == "Olá! Como posso ajudar?"


async def test_gemini_failure_changes_no_condo_data(
    conversation_client, scripted, empty_session, engine
):
    async def snapshot():
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT * FROM reservations ORDER BY 1"))
            vis = await conn.execute(text("SELECT * FROM visitors ORDER BY 1"))
            return res.fetchall(), vis.fetchall()

    before = await snapshot()
    scripted.main.script(sc.quota_error())
    r = await post(conversation_client, empty_session, {"texto": "Reserve a quadra."})
    assert r.status_code == 503
    assert await snapshot() == before


async def test_run_failure_returns_200_with_apology(conversation_client, scripted, empty_session):
    scripted.main.script(sc.tool_call("ferramenta_inexistente"), sc.text("Olá! Como posso ajudar?"))
    r = await post(conversation_client, empty_session, {"texto": "Olá"})
    assert r.status_code == 200
    assert r.json() == {"resposta": APOLOGY_MESSAGE, "confirmacoes_pendentes": []}
    r = await post(conversation_client, empty_session, {"texto": "Olá de novo"})
    assert r.json()["resposta"] == "Olá! Como posso ajudar?"


async def test_run_failure_keeps_pending(conversation_client, scripted, session_with_pending):
    scripted.main.script(sc.tool_call("ferramenta_inexistente"))
    r = await post(conversation_client, session_with_pending, {"texto": "Olá"})
    assert r.json()["resposta"] == APOLOGY_MESSAGE
    assert [i["id"] for i in r.json()["confirmacoes_pendentes"]] == PENDING_IDS


async def test_model_without_text_returns_fallback(conversation_client, scripted, empty_session):
    scripted.main.script(sc.empty_text())
    r = await post(conversation_client, empty_session, {"texto": "Olá"})
    assert r.json()["resposta"] == NO_REPLY_MESSAGE


async def test_session_store_failure_returns_503(conversation_client, empty_session, monkeypatch):
    service = conversation_client.app.state.session_service

    async def broken(*args, **kwargs):
        raise OperationalError("SELECT secret", {}, Exception("password aurora"))

    monkeypatch.setattr(service, "get_session", broken)
    r = await post(conversation_client, empty_session, {"texto": "Olá"})
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail and "SELECT" not in detail and "aurora:aurora" not in detail


async def test_messages_survive_app_restart(conversation_client, scripted, empty_session):
    scripted.main.script(sc.text("Olá! Como posso ajudar?"), sc.text("Segunda."))
    await post(conversation_client, empty_session, {"texto": "Olá"})
    before = [e["id"] for e in await events_of(conversation_client, empty_session)]

    app = create_app(get_settings())
    async with app.router.lifespan_context(app):
        app.state.runner = build_scripted_runner(scripted, app.state.session_service)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            after = [e["id"] for e in (await c.get(f"/sessoes/{empty_session.id}/eventos")).json()]
            assert after == before
            r = await c.post(f"/sessoes/{empty_session.id}/mensagens", json={"texto": "Outra"})
            assert r.status_code == 200 and r.json()["resposta"] == "Segunda."
            events = (await c.get(f"/sessoes/{empty_session.id}/eventos")).json()
            assert len(events) == 4


async def test_pending_survive_app_restart(scripted, session_with_pending):
    scripted.main.script(sc.text("Olá! Como posso ajudar?"))
    app = create_app(get_settings())
    async with app.router.lifespan_context(app):
        app.state.runner = build_scripted_runner(scripted, app.state.session_service)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.post(f"/sessoes/{session_with_pending.id}/mensagens", json={"texto": "Olá"})
    assert [i["id"] for i in r.json()["confirmacoes_pendentes"]] == PENDING_IDS
