from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from google.adk.sessions import Session
from pydantic import BaseModel, Field

from aurora.sessions.service import find_session, open_session

router = APIRouter()


class CreateSessionBody(BaseModel):
    apartamento: str = Field(min_length=1, max_length=10)


class CreateSessionResponse(BaseModel):
    session_id: str


async def require_session(session_id: str, request: Request) -> Session:
    session = await find_session(request.app.state.session_service, session_id=session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    return session


@router.post("/sessoes", status_code=201)
async def create_session(body: CreateSessionBody, request: Request) -> CreateSessionResponse:
    session = await open_session(
        request.app.state.session_service, request.app.state.engine, apartment=body.apartamento
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Apartamento não encontrado.")
    return CreateSessionResponse(session_id=session.id)


@router.get("/sessoes/{session_id}/eventos")
async def list_events(
    session: Annotated[Session, Depends(require_session)],
) -> list[dict[str, Any]]:
    return [
        event.model_dump(mode="json", by_alias=True, exclude_none=True) for event in session.events
    ]
