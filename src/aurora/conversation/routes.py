from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from google.adk.sessions import Session
from pydantic import BaseModel, StringConstraints

from aurora.conversation.service import ConversationResult, send_message
from aurora.sessions.routes import require_session

router = APIRouter()

MAX_TEXT_LENGTH = 2000


class MessageBody(BaseModel):
    texto: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TEXT_LENGTH)
    ]


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
