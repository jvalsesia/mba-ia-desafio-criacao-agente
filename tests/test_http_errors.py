from aurora.http_errors import UNAVAILABLE_MESSAGE, validation_message


async def test_validation_error_detail_is_text(client):
    r = await client.post("/sessoes", json={})
    assert isinstance(r.json()["detail"], str)


async def test_validation_error_names_the_field(client):
    r = await client.post("/sessoes", json={})
    assert "apartamento" in r.json()["detail"]


def test_validation_message_for_missing_body():
    assert "JSON" in validation_message([{"loc": ("body",), "type": "missing"}])


def test_unavailable_detail_has_no_internal_data():
    for bad in ("SELECT", "postgresql", "aurora:aurora", "segredo"):
        assert bad not in UNAVAILABLE_MESSAGE


async def test_unknown_route_detail_is_text(client):
    r = await client.get("/nao-existe")
    assert r.status_code == 404 and isinstance(r.json()["detail"], str)


async def test_assistant_unavailable_returns_503_with_text_detail():
    import httpx
    from fastapi import FastAPI

    from aurora.conversation.service import (
        ASSISTANT_UNAVAILABLE_MESSAGE,
        AssistantUnavailableError,
    )
    from aurora.http_errors import install_error_handlers

    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom")
    async def boom():
        raise AssistantUnavailableError()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/boom")
    assert r.status_code == 503
    assert r.json() == {"detail": ASSISTANT_UNAVAILABLE_MESSAGE}
