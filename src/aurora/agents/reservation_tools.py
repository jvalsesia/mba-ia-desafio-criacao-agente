import re
from collections.abc import Awaitable
from datetime import date

from google.adk.tools import FunctionTool, ToolContext
from sqlalchemy.ext.asyncio import AsyncEngine

from aurora.sessions.service import APARTMENT_KEY
from aurora.store import catalog, reservations
from aurora.store.errors import StoreError
from aurora.store.models import Availability, DateTaken, ReservationNotFound, UnknownArea

RESERVE_TOOL = "reservar_area"
CANCEL_TOOL = "cancelar_reserva"
LIST_TOOL = "listar_minhas_reservas"
AVAILABILITY_TOOL = "consultar_disponibilidade"
AREAS_TOOL = "listar_areas"

CONFIRMATION_HINT = "Reserva com taxa"

RESERVED = "reservada"
AWAITING_CONFIRMATION = "aguardando_confirmacao"
NOT_CONFIRMED = "nao_confirmada"
CANCELLED = "cancelada"
OK = "ok"
DATE_TAKEN = "data_indisponivel"
NOT_FOUND = "nao_encontrada"
INVALID_DATE = "data_invalida"
UNKNOWN_AREA = "area_desconhecida"
INVALID_PARAMETERS = "parametros_invalidos"
SERVICE_UNAVAILABLE = "servico_indisponivel"

MSG_AWAITING = "A reserva aguarda a confirmação do morador. Nada foi gravado."
MSG_DENIED = "A reserva não foi confirmada. Nada foi alterado."
MSG_TAKEN_ON_REQUEST = "Essa data não está disponível."
MSG_TAKEN_ON_APPROVAL = "Essa data não está mais disponível."
MSG_NOT_FOUND_BY_DATE = "Não encontrei uma reserva sua nessa data."
MSG_NOT_FOUND_BY_CODE = "Não encontrei uma reserva sua com esse código."
MSG_MISSING_IDENTIFICATION = "Informe a área e a data da reserva, ou o código."
MSG_INVALID_DATE = "Informe a data no formato AAAA-MM-DD."
MSG_UNKNOWN_AREA = "Área não encontrada."
MSG_SERVICE_UNAVAILABLE = "Não consegui concluir o pedido agora. Tente novamente em instantes."

_DATE_FORMAT = re.compile(r"\d{4}-\d{2}-\d{2}")


def _refusal(status: str, message: str) -> dict:
    return {"status": status, "mensagem": message}


def _unavailable() -> dict:
    return _refusal(SERVICE_UNAVAILABLE, MSG_SERVICE_UNAVAILABLE)


def _apartment(tool_context: ToolContext) -> str | None:
    return tool_context.state.get(APARTMENT_KEY)


def _parse_date(value: str) -> date | None:
    text = (value or "").strip()
    if not _DATE_FORMAT.fullmatch(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _normalize_area(value: str) -> str:
    return (value or "").strip().lower()


def _normalize_code(value: str) -> str:
    return (value or "").strip().upper()


async def _safe(work: Awaitable[dict]) -> dict:
    try:
        return await work
    except StoreError:
        return _unavailable()


def build_reservation_tools(engine: AsyncEngine) -> list[FunctionTool]:
    async def _list_reservations(tool_context: ToolContext) -> dict:
        apartment = _apartment(tool_context)
        if apartment is None:
            return _unavailable()
        found = await reservations.list_reservations(engine, apartment=apartment)
        return {
            "status": OK,
            "reservas": [
                {"codigo": r.code, "area": r.area_id, "data": r.day.isoformat()} for r in found
            ],
        }

    async def _check_availability(area: str, data: str, tool_context: ToolContext) -> dict:
        if _apartment(tool_context) is None:
            return _unavailable()
        day = _parse_date(data)
        if day is None:
            return _refusal(INVALID_DATE, MSG_INVALID_DATE)
        area_id = _normalize_area(area)
        result = await reservations.check_availability(engine, area_id=area_id, day=day)
        if isinstance(result, UnknownArea):
            return await _unknown_area()
        taken = result is Availability.TAKEN
        return {
            "status": OK,
            "area": area_id,
            "data": day.isoformat(),
            "disponibilidade": "ocupada" if taken else "livre",
        }

    async def _unknown_area() -> dict:
        known = await catalog.list_areas(engine)
        return {
            **_refusal(UNKNOWN_AREA, MSG_UNKNOWN_AREA),
            "areas": sorted(a.id for a in known),
        }

    async def _list_areas(tool_context: ToolContext) -> dict:
        if _apartment(tool_context) is None:
            return _unavailable()
        found = await catalog.list_areas(engine)
        return {
            "status": OK,
            "areas": [{"id": a.id, "nome": a.name, "taxa": float(a.fee)} for a in found],
        }

    async def listar_minhas_reservas(tool_context: ToolContext) -> dict:
        """Lista as reservas ativas do morador desta conversa.

        Não recebe parâmetros: o apartamento é conhecido pelo sistema.
        """
        return await _safe(_list_reservations(tool_context))

    async def consultar_disponibilidade(area: str, data: str, tool_context: ToolContext) -> dict:
        """Informa se uma área comum está livre ou ocupada em uma data.

        Args:
            area: id da área: salao-de-festas, churrasqueira ou quadra.
            data: data consultada, no formato AAAA-MM-DD.
        """
        return await _safe(_check_availability(area, data, tool_context))

    async def listar_areas(tool_context: ToolContext) -> dict:
        """Lista as áreas comuns reservadas com o nome e a taxa de cada uma.

        Não recebe parâmetros.
        """
        return await _safe(_list_areas(tool_context))

    return [
        FunctionTool(listar_minhas_reservas),
        FunctionTool(consultar_disponibilidade),
        FunctionTool(listar_areas),
    ]


__all__ = [
    "AREAS_TOOL",
    "AVAILABILITY_TOOL",
    "CANCEL_TOOL",
    "CONFIRMATION_HINT",
    "LIST_TOOL",
    "RESERVE_TOOL",
    "DateTaken",
    "ReservationNotFound",
    "build_reservation_tools",
]
