import logging

from google.adk.runners import Runner
from google.adk.sessions import Session
from google.genai import types

from aurora.conversation.pending import (
    REQUEST_CONFIRMATION_CALL,
    confirmation_result,
    pending_confirmations,
)
from aurora.conversation.service import ConversationResult, execute_turn
from aurora.sessions.service import AuroraSessionService, SessionStoreError, find_session

NOT_PENDING_MESSAGE = "Não existe confirmação pendente com esse id nesta sessão."
NOT_EXECUTED_MESSAGE = (
    "Não consegui executar a ação agora. A confirmação continua pendente e pode ser respondida "
    "de novo."
)
APPROVED_MESSAGE = "Confirmação recebida. A ação foi executada."
DENIED_MESSAGE = "Confirmação negada. Nada foi alterado."

logger = logging.getLogger("aurora.conversation")


def _answer_message(confirmation_id: str, confirmed: bool) -> types.Content:
    return types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=confirmation_id,
                    name=REQUEST_CONFIRMATION_CALL,
                    response={"confirmed": confirmed},
                )
            )
        ],
    )


def _outcome_text(texts: list[str], result: dict, confirmed: bool) -> str:
    text = "\n".join(texts)
    if text:
        return text
    message = result.get("mensagem")
    if isinstance(message, str) and message:
        return message
    return APPROVED_MESSAGE if confirmed else DENIED_MESSAGE


async def answer_confirmation(
    resume_runners: dict[str, Runner],
    service: AuroraSessionService,
    session: Session,
    *,
    confirmation_id: str,
    confirmed: bool,
) -> ConversationResult | None:
    item = next((p for p in pending_confirmations(session) if p.id == confirmation_id), None)
    if item is None:
        return None

    texts: list[str] = []
    runner = resume_runners.get(item.requester)
    if runner is not None:
        try:
            output = await execute_turn(
                runner, session, _answer_message(confirmation_id, confirmed)
            )
            texts = output.texts
        except SessionStoreError:
            raise
        except Exception as exc:
            logger.error("resume failed: %s session=%s", type(exc).__name__, session.id)

    current = await find_session(service, session_id=session.id)
    if current is None:
        raise SessionStoreError()
    pending = pending_confirmations(current)
    result = confirmation_result(current, confirmation_id)
    if result is None:
        return ConversationResult(NOT_EXECUTED_MESSAGE, pending)
    return ConversationResult(_outcome_text(texts, result, confirmed), pending)
