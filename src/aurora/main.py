from contextlib import asynccontextmanager

from fastapi import FastAPI

from aurora.config import Settings, get_settings
from aurora.db import create_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resolved = settings or get_settings()
        app.state.settings = resolved
        app.state.engine = create_engine(resolved)
        try:
            yield
        finally:
            await app.state.engine.dispose()

    app = FastAPI(title="Aurora", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
