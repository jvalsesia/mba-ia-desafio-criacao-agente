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


async def test_lifespan_exposes_session_service():
    app = create_app()
    async with app.router.lifespan_context(app):
        assert app.state.session_service is not None


async def test_lifespan_exposes_runner():
    app = create_app()
    async with app.router.lifespan_context(app):
        assert app.state.runner.session_service is app.state.session_service


async def test_lifespan_wires_reservation_tools():
    app = create_app()
    async with app.router.lifespan_context(app):
        agent = app.state.runner.app.root_agent.find_sub_agent("reservas")
        assert [t.name for t in agent.tools] == [
            "reservar_area",
            "cancelar_reserva",
            "listar_minhas_reservas",
            "consultar_disponibilidade",
            "listar_areas",
        ]


async def test_lifespan_wires_visitor_tools():
    app = create_app()
    async with app.router.lifespan_context(app):
        agent = app.state.runner.app.root_agent.find_sub_agent("visitantes")
        assert [t.name for t in agent.tools] == ["autorizar_visitante", "listar_meus_visitantes"]
