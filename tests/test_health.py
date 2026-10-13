import httpx

from aurora.main import create_app


async def test_health_returns_ok():
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_health_is_json():
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/health")
    assert r.headers["content-type"].startswith("application/json")


async def test_lifespan_creates_and_disposes_engine():
    app = create_app()
    async with app.router.lifespan_context(app):
        engine = app.state.engine
        assert engine is not None
    assert engine.pool.checkedout() == 0
