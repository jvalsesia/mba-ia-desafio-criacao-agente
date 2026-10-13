from google.adk.apps import App
from google.adk.models import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService

from aurora.agents.assistant import build_assistant
from aurora.sessions.service import APP_NAME


def build_app(*, main_model: str | BaseLlm, specialists_model: str | BaseLlm) -> App:
    root = build_assistant(model=main_model, specialists_model=specialists_model)
    return App(name=APP_NAME, root_agent=root)


def build_runner(app: App, session_service: BaseSessionService) -> Runner:
    return Runner(app=app, session_service=session_service, auto_create_session=False)
