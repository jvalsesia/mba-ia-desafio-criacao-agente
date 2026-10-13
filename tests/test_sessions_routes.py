import pytest
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.genai import types
from sqlalchemy import text

from aurora.sessions.service import SessionStoreError, find_session, session_apartment
from aurora.store.errors import StoreError


async def count_sessions(engine):
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT count(*) FROM sessions"))).scalar_one()


async def test_create_session_returns_201_and_id(client):
    r = await client.post("/sessoes", json={"apartamento": "101"})
    assert r.status_code == 201
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["session_id"]


async def test_create_session_accepts_all_six_apartments(client):
    ids = set()
    for n in ("101", "102", "201", "202", "301", "302"):
        r = await client.post("/sessoes", json={"apartamento": n})
        assert r.status_code == 201
        ids.add(r.json()["session_id"])
    assert len(ids) == 6


async def test_create_session_unknown_apartment_returns_404(client, engine):
    r = await client.post("/sessoes", json={"apartamento": "999"})
    assert r.status_code == 404
    assert isinstance(r.json()["detail"], str)
    assert await count_sessions(engine) == 0


async def test_create_session_missing_field_returns_422(client, engine):
    r = await client.post("/sessoes", json={})
    assert r.status_code == 422
    assert "apartamento" in r.json()["detail"]
    assert await count_sessions(engine) == 0


async def test_create_session_non_string_returns_422(client, engine):
    r = await client.post("/sessoes", json={"apartamento": 101})
    assert r.status_code == 422
    assert await count_sessions(engine) == 0


async def test_create_session_malformed_json_returns_422(client, engine):
    r = await client.post(
        "/sessoes", content='{"apartamento": ', headers={"content-type": "application/json"}
    )
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str) and r.json()["detail"]
    assert await count_sessions(engine) == 0


async def test_create_session_ignores_client_session_id(client):
    a = (await client.post("/sessoes", json={"apartamento": "101"})).json()["session_id"]
    r = await client.post("/sessoes", json={"apartamento": "302", "session_id": a})
    assert r.status_code == 201 and r.json()["session_id"] != a
    s = await find_session(client.app.state.session_service, session_id=a)
    assert session_apartment(s) == "101"


async def test_create_session_does_not_call_model(client):
    r = await client.post("/sessoes", json={"apartamento": "101"})
    assert r.status_code == 201


async def test_events_of_new_session_is_empty_list(client):
    sid = (await client.post("/sessoes", json={"apartamento": "101"})).json()["session_id"]
    r = await client.get(f"/sessoes/{sid}/eventos")
    assert r.status_code == 200 and r.json() == []


async def test_events_returns_all_in_order(client, session_with_history):
    r = await client.get(f"/sessoes/{session_with_history.id}/eventos")
    assert r.status_code == 200
    ids = [e["id"] for e in r.json()]
    assert len(ids) == 4 and ids == [e.id for e in session_with_history.events]


async def test_events_carry_full_content(client, session_with_history):
    ev = (await client.get(f"/sessoes/{session_with_history.id}/eventos")).json()
    assert ev[0]["author"] == "user"
    assert ev[0]["content"]["parts"][0]["text"] == "Quais são as minhas reservas?"
    assert ev[1]["content"]["parts"][0]["functionCall"]["id"] == "fc-1"
    assert "RSV-1377" in str(ev[2]["content"]["parts"][0]["functionResponse"]["response"])
    assert ev[3]["content"]["parts"][0]["functionCall"]["name"] == "reservar_area"
    assert ev[3]["actions"]["requestedToolConfirmations"]["fc-2"]["payload"]["taxa"] == 150.0


async def test_events_never_expose_apartment_in_state_delta(client):
    sid = (await client.post("/sessoes", json={"apartamento": "101"})).json()["session_id"]
    svc = client.app.state.session_service
    s = await find_session(svc, session_id=sid)
    ev = Event(
        author="user",
        invocation_id="i",
        content=types.Content(role="user", parts=[types.Part(text="x")]),
        actions=EventActions(state_delta={"apartamento": "302"}),
    )
    await svc.append_event(s, ev)
    body = (await client.get(f"/sessoes/{sid}/eventos")).json()
    assert len(body) == 1
    assert all("apartamento" not in e["actions"].get("stateDelta", {}) for e in body)


async def test_events_unknown_session_returns_404(client):
    r = await client.get("/sessoes/sessao-inexistente/eventos")
    assert r.status_code == 404 and isinstance(r.json()["detail"], str)


async def test_events_count_survives_app_restart(client, session_with_history):
    from aurora.config import get_settings
    from aurora.main import create_app

    before = (await client.get(f"/sessoes/{session_with_history.id}/eventos")).json()
    import httpx

    app = create_app(get_settings())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as c2:
            after = (await c2.get(f"/sessoes/{session_with_history.id}/eventos")).json()
    assert [e["id"] for e in after] == [e["id"] for e in before]


async def test_no_route_mutates_a_session(client):
    sid = (await client.post("/sessoes", json={"apartamento": "101"})).json()["session_id"]
    for method in ("PUT", "PATCH", "DELETE"):
        for path in (f"/sessoes/{sid}", f"/sessoes/{sid}/eventos"):
            r = await client.request(method, path, json={"apartamento": "302"})
            assert r.status_code in (404, 405)
    s = await find_session(client.app.state.session_service, session_id=sid)
    assert session_apartment(s) == "101"


class _Failing:
    async def close(self):
        pass

    async def create_session(self, **k):
        raise SessionStoreError()

    async def get_session(self, **k):
        raise SessionStoreError()


async def test_session_store_failure_returns_503(client, engine):
    client.app.state.session_service = _Failing()
    r = await client.post("/sessoes", json={"apartamento": "101"})
    assert r.status_code == 503
    assert r.json() == {"detail": "Serviço indisponível no momento. Tente novamente."}
    assert (await client.get("/sessoes/x/eventos")).status_code == 503
    assert await count_sessions(engine) == 0


async def test_catalog_failure_returns_503(client, monkeypatch):
    async def boom(*a, **k):
        raise StoreError()

    monkeypatch.setattr("aurora.sessions.service.get_apartment", boom)
    r = await client.post("/sessoes", json={"apartamento": "101"})
    assert r.status_code == 503
    assert r.json() == {"detail": "Serviço indisponível no momento. Tente novamente."}


_ = pytest
