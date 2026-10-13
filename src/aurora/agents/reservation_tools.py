import re
from collections.abc import Awaitable
from datetime import date

from google.adk.tools import FunctionTool, ToolContext
from sqlalchemy.ext.asyncio import AsyncEngine

from aurora.sessions.service import APARTMENT_KEY
from aurora.store import catalog, reservations
from aurora.store.errors import StoreError
from aurora.store.models import (
    Availability,
    DateTaken,
    Reservation,
    ReservationNotFound,
    UnknownArea,
)

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


def _reservation_fields(reservation: Reservation) -> dict:
    return {
        "codigo": reservation.code,
        "area": reservation.area_id,
        "data": reservation.day.isoformat(),
    }


def build_reservation_tools(engine: AsyncEngine) -> list[FunctionTool]:
    async def _reserve(area: str, data: str, tool_context: ToolContext) -> dict:
        apartment = _apartment(tool_context)
        if apartment is None:
            return _unavailable()
        day = _parse_date(data)
        if day is None:
            return _refusal(INVALID_DATE, MSG_INVALID_DATE)
        area_id = _normalize_area(area)
        found = await catalog.get_area(engine, area_id=area_id)
        if found is None:
            return await _unknown_area()
        fee = float(found.fee)
        answer = tool_context.tool_confirmation
        if fee > 0 and answer is None:
            availability = await reservations.check_availability(engine, area_id=area_id, day=day)
            if availability is Availability.TAKEN:
                return _refusal(DATE_TAKEN, MSG_TAKEN_ON_REQUEST)
            payload = {"area": area_id, "data": day.isoformat(), "taxa": fee}
            tool_context.request_confirmation(hint=CONFIRMATION_HINT, payload=payload)
            tool_context.actions.skip_summarization = True
            return {"status": AWAITING_CONFIRMATION, **payload, "mensagem": MSG_AWAITING}
        if fee > 0 and not answer.confirmed:
            return _refusal(NOT_CONFIRMED, MSG_DENIED)
        approved = fee > 0
        created = await reservations.create_reservation(
            engine, apartment=apartment, area_id=area_id, day=day
        )
        if isinstance(created, DateTaken):
            message = MSG_TAKEN_ON_APPROVAL if approved else MSG_TAKEN_ON_REQUEST
            return _refusal(DATE_TAKEN, message)
        if isinstance(created, UnknownArea):
            return await _unknown_area()
        return {"status": RESERVED, **_reservation_fields(created), "taxa": fee}

    async def _cancel(area: str, data: str, codigo: str, tool_context: ToolContext) -> dict:
        apartment = _apartment(tool_context)
        if apartment is None:
            return _unavailable()
        code = _normalize_code(codigo)
        if code:
            not_found = _refusal(NOT_FOUND, MSG_NOT_FOUND_BY_CODE)
        else:
            area_id = _normalize_area(area)
            if not area_id or not (data or "").strip():
                return _refusal(INVALID_PARAMETERS, MSG_MISSING_IDENTIFICATION)
            day = _parse_date(data)
            if day is None:
                return _refusal(INVALID_DATE, MSG_INVALID_DATE)
            not_found = _refusal(NOT_FOUND, MSG_NOT_FOUND_BY_DATE)
            active = await reservations.list_reservations(engine, apartment=apartment)
            match = next((r for r in active if r.area_id == area_id and r.day == day), None)
            if match is None:
                return not_found
            code = match.code
        result = await reservations.cancel_reservation(engine, apartment=apartment, code=code)
        if isinstance(result, ReservationNotFound):
            return not_found
        return {"status": CANCELLED, **_reservation_fields(result)}

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

    async def reservar_area(area: str, data: str, tool_context: ToolContext) -> dict:
        """Reserva uma área comum para o morador desta conversa.

        Áreas com taxa ficam aguardando a confirmação do morador antes de gravar.

        Args:
            area: id da área: salao-de-festas, churrasqueira ou quadra.
            data: data da reserva, no formato AAAA-MM-DD.
        """
        return await _safe(_reserve(area, data, tool_context))

    async def cancelar_reserva(
        tool_context: ToolContext, area: str = "", data: str = "", codigo: str = ""
    ) -> dict:
        """Cancela uma reserva do próprio morador, por área e data ou pelo código.

        Args:
            area: id da área da reserva, usado junto com a data.
            data: data da reserva, no formato AAAA-MM-DD.
            codigo: código da reserva; tem precedência sobre a área e a data.
        """
        return await _safe(_cancel(area, data, codigo, tool_context))

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
        FunctionTool(reservar_area),
        FunctionTool(cancelar_reserva),
        FunctionTool(listar_minhas_reservas),
        FunctionTool(consultar_disponibilidade),
        FunctionTool(listar_areas),
    ]
