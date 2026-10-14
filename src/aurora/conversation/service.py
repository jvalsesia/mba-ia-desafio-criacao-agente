import logging
from dataclasses import dataclass

import httpx
from google.adk.runners import Runner
from google.adk.sessions import Session
from google.genai import errors as genai_errors
from google.genai import types
from sqlalchemy.exc import SQLAlchemyError

from aurora.conversation.pending import PendingConfirmation, pending_confirmations
from aurora.sessions.service import USER_ID, AuroraSessionService, SessionStoreError, find_session

ASSISTANT_UNAVAILABLE_MESSAGE = "Assistente temporariamente indisponível. Tente novamente."
APOLOGY_MESSAGE = "Desculpe, não consegui concluir o seu pedido. Tente novamente."
NO_REPLY_MESSAGE = "Desculpe, não consegui responder agora. Pode repetir o pedido?"

logger = logging.getLogger("aurora.conversation")


class AssistantUnavailableError(Exception):
    """The model could not be reached or refused the call; never carries keys or provider text."""

    def __init__(self) -> None:
        super().__init__(ASSISTANT_UNAVAILABLE_MESSAGE)


@dataclass(frozen=True)
class ConversationResult:
    reply: str
    pending: list[PendingConfirmation]


def _final_texts(event) -> list[str]:
    if event.author == "user" or event.partial or not event.content or not event.content.parts:
        return []
    parts = event.content.parts
    if any(p.function_call or p.function_response for p in parts):
        return []
    return [p.text for p in parts if p.text and not p.thought]


async def _reread_pending(service: AuroraSessionService, session: Session):
    current = await find_session(service, session_id=session.id)
    return pending_confirmations(current) if current is not None else []


def _is_request_confirmation(event) -> bool:
    return any(
        p.function_call and p.function_call.name == "adk_request_confirmation"
        for p in (event.content.parts if event.content and event.content.parts else [])
    )


@dataclass(frozen=True)
class TurnOutput:
    texts: list[str]
    paused: bool


async def execute_turn(runner: Runner, session: Session, message: types.Content) -> TurnOutput:
    texts: list[str] = []
    paused = False
    try:
        async for event in runner.run_async(
            user_id=USER_ID, session_id=session.id, new_message=message
        ):
            texts.extend(_final_texts(event))
            paused = paused or _is_request_confirmation(event)
    except (genai_errors.APIError, httpx.TransportError) as exc:
        logger.error("model unavailable: %s session=%s", type(exc).__name__, session.id)
        raise AssistantUnavailableError() from exc
    except (SQLAlchemyError, OSError) as exc:
        logger.error("session store failure: %s session=%s", type(exc).__name__, session.id)
        raise SessionStoreError() from exc
    return TurnOutput(texts, paused)


async def run_turn(
    runner: Runner,
    service: AuroraSessionService,
    session: Session,
    message: types.Content,
) -> ConversationResult:
    try:
        output = await execute_turn(runner, session, message)
    except (AssistantUnavailableError, SessionStoreError):
        raise
    except Exception as exc:
        logger.error("turn failed: %s session=%s", type(exc).__name__, session.id)
        return ConversationResult(APOLOGY_MESSAGE, await _reread_pending(service, session))

    pending = await _reread_pending(service, session)
    reply = "\n".join(output.texts)
    if not reply:
        reply = "" if output.paused else NO_REPLY_MESSAGE
    return ConversationResult(reply, pending)


async def send_message(
    runner: Runner, service: AuroraSessionService, session: Session, *, text: str
) -> ConversationResult:
    message = types.Content(role="user", parts=[types.Part(text=text)])
    return await run_turn(runner, service, session, message)
