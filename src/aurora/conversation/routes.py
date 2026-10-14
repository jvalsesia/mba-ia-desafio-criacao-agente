from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from google.adk.sessions import Session
from pydantic import BaseModel, StrictBool, StringConstraints

from aurora.conversation.confirmations import NOT_PENDING_MESSAGE, answer_confirmation
from aurora.conversation.service import ConversationResult, send_message
from aurora.sessions.routes import require_session

router = APIRouter()

MAX_TEXT_LENGTH = 2000


class MessageBody(BaseModel):
    texto: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TEXT_LENGTH)
    ]


class ConfirmationBody(BaseModel):
    id: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]
    confirmado: StrictBool


class PendingItem(BaseModel):
    id: str
    acao: str
    detalhes: dict[str, Any]


class MessageResponse(BaseModel):
    resposta: str
    confirmacoes_pendentes: list[PendingItem]


def to_message_response(result: ConversationResult) -> MessageResponse:
    return MessageResponse(
        resposta=result.reply,
        confirmacoes_pendentes=[
            PendingItem(id=p.id, acao=p.action, detalhes=p.details) for p in result.pending
        ],
    )


@router.post("/sessoes/{session_id}/mensagens")
async def post_message(
    body: MessageBody,
    session: Annotated[Session, Depends(require_session)],
    request: Request,
) -> MessageResponse:
    result = await send_message(
        request.app.state.runner,
        request.app.state.session_service,
        session,
        text=body.texto,
    )
    return to_message_response(result)


@router.post("/sessoes/{session_id}/confirmacoes")
async def post_confirmation(
    body: ConfirmationBody,
    session: Annotated[Session, Depends(require_session)],
    request: Request,
) -> MessageResponse:
    result = await answer_confirmation(
        request.app.state.resume_runners,
        request.app.state.session_service,
        session,
        confirmation_id=body.id,
        confirmed=body.confirmado,
    )
    if result is None:
        raise HTTPException(status_code=409, detail=NOT_PENDING_MESSAGE)
    return to_message_response(result)
