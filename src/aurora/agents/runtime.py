from pathlib import Path

from google.adk.apps import App
from google.adk.models import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from sqlalchemy.ext.asyncio import AsyncEngine

from aurora.agents.assistant import build_assistant
from aurora.agents.bylaws_document import load_bylaws
from aurora.agents.reservations import RESERVATIONS_NAME, build_reservations_agent
from aurora.agents.visitors import VISITORS_NAME, build_visitors_agent
from aurora.config import DATA_DIR
from aurora.sessions.service import APP_NAME


def build_app(
    *,
    main_model: str | BaseLlm,
    specialists_model: str | BaseLlm,
    engine: AsyncEngine,
    data_dir: Path = DATA_DIR,
) -> App:
    root = build_assistant(
        model=main_model,
        specialists_model=specialists_model,
        engine=engine,
        bylaws=load_bylaws(data_dir),
    )
    return App(name=APP_NAME, root_agent=root)


def build_runner(app: App, session_service: BaseSessionService) -> Runner:
    return Runner(app=app, session_service=session_service, auto_create_session=False)


def build_resume_runners(
    *,
    specialists_model: str | BaseLlm,
    engine: AsyncEngine,
    session_service: BaseSessionService,
) -> dict[str, Runner]:
    """One Runner per specialist that asks for confirmation, keyed by the agent name."""
    agents = {
        RESERVATIONS_NAME: build_reservations_agent(specialists_model, engine),
        VISITORS_NAME: build_visitors_agent(specialists_model, engine),
    }
    return {
        name: Runner(
            app_name=APP_NAME,
            agent=agent,
            session_service=session_service,
            auto_create_session=False,
        )
        for name, agent in agents.items()
    }
