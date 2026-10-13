from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from aurora.conversation.service import ASSISTANT_UNAVAILABLE_MESSAGE, AssistantUnavailableError
from aurora.sessions.service import SessionStoreError
from aurora.store.errors import StoreError

UNAVAILABLE_MESSAGE = "Serviço indisponível no momento. Tente novamente."
INVALID_BODY_MESSAGE = "Requisição inválida: envie um corpo JSON válido."


def _fields_message(fields: list[str]) -> str:
    label = "o campo" if len(fields) == 1 else "os campos"
    return f"Requisição inválida: verifique {label} {', '.join(fields)}."


def validation_message(errors: list[dict]) -> str:
    fields: list[str] = []
    for err in errors:
        loc = err.get("loc", ())
        if err.get("type") == "json_invalid" or tuple(loc) == ("body",):
            return INVALID_BODY_MESSAGE
        name = str(loc[-1]) if loc else ""
        if name and name not in fields:
            fields.append(name)
    return _fields_message(fields) if fields else INVALID_BODY_MESSAGE


async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": validation_message(exc.errors())})


async def _unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": UNAVAILABLE_MESSAGE})


async def _assistant_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": ASSISTANT_UNAVAILABLE_MESSAGE})


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(SessionStoreError, _unavailable_handler)
    app.add_exception_handler(StoreError, _unavailable_handler)
    app.add_exception_handler(AssistantUnavailableError, _assistant_unavailable_handler)
