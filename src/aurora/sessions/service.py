import functools
from collections.abc import Awaitable, Callable

from google.adk.events.event import Event
from google.adk.sessions import DatabaseSessionService, Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from aurora.config import Settings
from aurora.store.catalog import get_apartment

APP_NAME = "aurora"
USER_ID = "morador"
APARTMENT_KEY = "apartamento"

GENERIC_MESSAGE = "Armazenamento de sessões indisponível no momento."


class SessionStoreError(Exception):
    """Infrastructure failure in the session store; never carries SQL, URLs or passwords."""

    def __init__(self, message: str = GENERIC_MESSAGE) -> None:
        super().__init__(message)


def translate_session_errors[**P, R](func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Turn driver and connection failures into SessionStoreError, keeping the cause chained."""

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await func(*args, **kwargs)
        except (SQLAlchemyError, OSError) as exc:
            raise SessionStoreError() from exc

    return wrapper


class AuroraSessionService(DatabaseSessionService):
    """Database session service that never persists a change to the apartment key."""

    async def append_event(self, session: Session, event: Event) -> Event:
        if event.actions is not None and event.actions.state_delta:
            event.actions.state_delta.pop(APARTMENT_KEY, None)
        return await super().append_event(session, event)


def create_session_service(settings: Settings) -> AuroraSessionService:
    return AuroraSessionService(settings.database_url)


@translate_session_errors
async def open_session(
    service: AuroraSessionService, engine: AsyncEngine, *, apartment: str
) -> Session | None:
    if await get_apartment(engine, number=apartment) is None:
        return None
    return await service.create_session(
        app_name=APP_NAME, user_id=USER_ID, state={APARTMENT_KEY: apartment}
    )


@translate_session_errors
async def find_session(service: AuroraSessionService, *, session_id: str) -> Session | None:
    return await service.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)


def session_apartment(session: Session) -> str:
    return session.state[APARTMENT_KEY]
