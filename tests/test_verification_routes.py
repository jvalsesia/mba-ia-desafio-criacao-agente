import ast
import inspect
from datetime import date

import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from aurora.main import create_app
from aurora.store.reservations import cancel_reservation, create_reservation
from aurora.store.visitors import create_visitor
from aurora.verification import routes

R101 = {"codigo": "RSV-1377", "area": "quadra", "data": "2030-03-09"}
V302 = {"nome": "Marina Duarte", "data": "2030-03-16"}


@pytest.fixture
async def api(seeded):
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            client.app = app
            yield client


async def test_reservations_of_101_with_seed_data(api):
    r = await api.get("/apartamentos/101/reservas")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == [R101]


async def test_reservation_item_has_only_documented_fields(api):
    r = await api.get("/apartamentos/101/reservas")
    assert set(r.json()[0]) == {"codigo", "area", "data"}


async def test_reservations_are_scoped_to_apartment(api):
    r = await api.get("/apartamentos/302/reservas")
    assert r.json() == [{"codigo": "RSV-4821", "area": "salao-de-festas", "data": "2030-03-16"}]


async def test_cancelled_reservation_is_not_listed(api, seeded):
    await cancel_reservation(seeded, apartment="101", code="RSV-1377")
    r = await api.get("/apartamentos/101/reservas")
    assert r.status_code == 200
    assert r.json() == []


async def test_new_reservation_is_listed(api, seeded):
    new = await create_reservation(
        seeded, apartment="101", area_id="churrasqueira", day=date(2030, 4, 10)
    )
    other = await create_reservation(
        seeded, apartment="101", area_id="salao-de-festas", day=date(2030, 4, 12)
    )
    await cancel_reservation(seeded, apartment="101", code=other.code)
    body = (await api.get("/apartamentos/101/reservas")).json()
    assert body == [R101, {"codigo": new.code, "area": "churrasqueira", "data": "2030-04-10"}]


async def test_reservations_ordered_by_date_then_code(api, seeded):
    await create_reservation(
        seeded, apartment="101", area_id="salao-de-festas", day=date(2030, 3, 1)
    )
    last = await create_reservation(
        seeded, apartment="101", area_id="churrasqueira", day=date(2030, 3, 9)
    )
    body = (await api.get("/apartamentos/101/reservas")).json()
    assert [b["data"] for b in body] == ["2030-03-01", "2030-03-09", "2030-03-09"]
    assert body[1] == R101
    assert body[2]["codigo"] == last.code > "RSV-1377"


async def test_reservations_empty_for_apartment_without_records(api):
    r = await api.get("/apartamentos/102/reservas")
    assert r.status_code == 200
    assert r.json() == []


async def test_reservations_unknown_apartment_returns_404(api):
    r = await api.get("/apartamentos/999/reservas")
    assert r.status_code == 404
    assert r.json() == {"detail": "Apartamento não encontrado."}


async def test_visitors_of_302_with_seed_data(api):
    r = await api.get("/apartamentos/302/visitantes")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == [V302]


async def test_visitor_item_has_only_documented_fields(api):
    r = await api.get("/apartamentos/302/visitantes")
    assert set(r.json()[0]) == {"nome", "data"}


async def test_visitors_are_scoped_to_apartment(api):
    r = await api.get("/apartamentos/201/visitantes")
    assert r.json() == [{"nome": "Paulo Nogueira", "data": "2030-03-23"}]


async def test_new_visitor_is_listed_in_order(api, seeded):
    await create_visitor(seeded, apartment="302", name="Zeca Prado", day=date(2030, 3, 10))
    await create_visitor(seeded, apartment="302", name="Ana Lima", day=date(2030, 3, 16))
    body = (await api.get("/apartamentos/302/visitantes")).json()
    assert body == [
        {"nome": "Zeca Prado", "data": "2030-03-10"},
        {"nome": "Ana Lima", "data": "2030-03-16"},
        V302,
    ]


async def test_visitors_empty_for_apartment_without_records(api):
    r = await api.get("/apartamentos/101/visitantes")
    assert r.status_code == 200
    assert r.json() == []


async def test_visitors_unknown_apartment_returns_404(api):
    r = await api.get("/apartamentos/999/visitantes")
    assert r.status_code == 404
    assert isinstance(r.json()["detail"], str) and r.json()["detail"]


async def test_routes_answer_without_gemini_key(api, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert (await api.get("/apartamentos/101/reservas")).json() == [R101]
    assert (await api.get("/apartamentos/302/visitantes")).json() == [V302]


def test_module_does_not_import_model_or_sessions():
    tree = ast.parse(inspect.getsource(routes))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    for name in names:
        assert not name.startswith(("google.adk", "google.genai", "aurora.sessions"))


@pytest.mark.parametrize("path", ["reservas", "visitantes"])
async def test_store_error_becomes_503(path):
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.engine = create_async_engine(
            "postgresql+asyncpg://aurora:secretpw@localhost:1/aurora_test"
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.get(f"/apartamentos/101/{path}")
        await app.state.engine.dispose()
    assert r.status_code == 503
    assert r.json() == {"detail": "Serviço indisponível no momento. Tente novamente."}
    assert "secretpw" not in r.text and "SELECT" not in r.text


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
async def test_write_methods_are_not_allowed(api, method):
    r = await api.request(method, "/apartamentos/101/reservas")
    assert r.status_code == 405
    r = await api.request(method, "/apartamentos/302/visitantes")
    assert r.status_code == 405
    assert (await api.get("/apartamentos/101/reservas")).json() == [R101]
    assert (await api.get("/apartamentos/302/visitantes")).json() == [V302]


async def test_apartment_number_is_matched_exactly(api):
    assert (await api.get("/apartamentos/101 /reservas")).status_code == 404
