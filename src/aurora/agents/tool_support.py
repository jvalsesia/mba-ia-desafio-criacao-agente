import re
from collections.abc import Awaitable
from datetime import date

from google.adk.tools import ToolContext

from aurora.sessions.service import APARTMENT_KEY
from aurora.store.errors import StoreError

OK = "ok"
AWAITING_CONFIRMATION = "aguardando_confirmacao"
NOT_CONFIRMED = "nao_confirmada"
INVALID_DATE = "data_invalida"
SERVICE_UNAVAILABLE = "servico_indisponivel"

MSG_INVALID_DATE = "Informe a data no formato AAAA-MM-DD."
MSG_SERVICE_UNAVAILABLE = "Não consegui concluir o pedido agora. Tente novamente em instantes."

_DATE_FORMAT = re.compile(r"\d{4}-\d{2}-\d{2}")


def refusal(status: str, message: str) -> dict:
    return {"status": status, "mensagem": message}


def unavailable() -> dict:
    return refusal(SERVICE_UNAVAILABLE, MSG_SERVICE_UNAVAILABLE)


def apartment_of(tool_context: ToolContext) -> str | None:
    return tool_context.state.get(APARTMENT_KEY)


def parse_date(value: str) -> date | None:
    text = (value or "").strip()
    if not _DATE_FORMAT.fullmatch(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


async def safe(work: Awaitable[dict]) -> dict:
    try:
        return await work
    except StoreError:
        return unavailable()
