from contextlib import asynccontextmanager

from fastapi import FastAPI

from aurora.agents.runtime import build_app, build_runner
from aurora.config import Settings, get_settings
from aurora.conversation.routes import router as conversation_router
from aurora.db import create_engine
from aurora.http_errors import install_error_handlers
from aurora.sessions.routes import router as sessions_router
from aurora.sessions.service import create_session_service
from aurora.verification.routes import router as verification_router


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resolved = settings or get_settings()
        app.state.settings = resolved
        app.state.engine = create_engine(resolved)
        app.state.session_service = create_session_service(resolved)
        app.state.runner = build_runner(
            build_app(
                main_model=resolved.gemini_model_main,
                specialists_model=resolved.gemini_model_specialists,
            ),
            app.state.session_service,
        )
        try:
            yield
        finally:
            await app.state.runner.close()
            await app.state.session_service.close()
            await app.state.engine.dispose()

    app = FastAPI(title="Aurora", lifespan=lifespan)

    install_error_handlers(app)
    app.include_router(sessions_router)
    app.include_router(conversation_router)
    app.include_router(verification_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
