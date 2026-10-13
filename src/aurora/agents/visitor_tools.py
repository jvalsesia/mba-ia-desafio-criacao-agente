from google.adk.tools import FunctionTool, ToolContext
from sqlalchemy.ext.asyncio import AsyncEngine

from aurora.agents.tool_support import (
    AWAITING_CONFIRMATION,
    INVALID_DATE,
    MSG_INVALID_DATE,
    NOT_CONFIRMED,
    OK,
    apartment_of,
    parse_date,
    refusal,
    safe,
    unavailable,
)
from aurora.store import visitors
from aurora.store.models import AlreadyAuthorized

AUTHORIZE_TOOL = "autorizar_visitante"
LIST_TOOL = "listar_meus_visitantes"

CONFIRMATION_HINT = "Liberação de acesso"

AUTHORIZED = "autorizado"
ALREADY_AUTHORIZED = "ja_autorizado"
INVALID_NAME = "nome_invalido"

MSG_AWAITING = "A autorização aguarda a confirmação do morador. Nada foi gravado."
MSG_DENIED = "A autorização não foi confirmada. Nada foi alterado."
MSG_ALREADY_AUTHORIZED = "Esse visitante já está autorizado nessa data."
MSG_INVALID_NAME = "Informe o nome do visitante, com 2 a 100 caracteres."

_NAME_MIN = 2
_NAME_MAX = 100


def build_visitor_tools(engine: AsyncEngine) -> list[FunctionTool]:
    async def _authorize(nome: str, data: str, tool_context: ToolContext) -> dict:
        apartment = apartment_of(tool_context)
        if apartment is None:
            return unavailable()
        name = visitors.normalize_name(nome or "")
        if not _NAME_MIN <= len(name) <= _NAME_MAX:
            return refusal(INVALID_NAME, MSG_INVALID_NAME)
        day = parse_date(data)
        if day is None:
            return refusal(INVALID_DATE, MSG_INVALID_DATE)
        answer = tool_context.tool_confirmation
        if answer is None:
            current = await visitors.list_visitors(engine, apartment=apartment)
            if any(v.day == day and v.name.lower() == name.lower() for v in current):
                return refusal(ALREADY_AUTHORIZED, MSG_ALREADY_AUTHORIZED)
            payload = {"nome": name, "data": day.isoformat()}
            tool_context.request_confirmation(hint=CONFIRMATION_HINT, payload=payload)
            tool_context.actions.skip_summarization = True
            return {"status": AWAITING_CONFIRMATION, **payload, "mensagem": MSG_AWAITING}
        if not answer.confirmed:
            return refusal(NOT_CONFIRMED, MSG_DENIED)
        created = await visitors.create_visitor(engine, apartment=apartment, name=name, day=day)
        if isinstance(created, AlreadyAuthorized):
            return refusal(ALREADY_AUTHORIZED, MSG_ALREADY_AUTHORIZED)
        return {"status": AUTHORIZED, "nome": created.name, "data": created.day.isoformat()}

    async def _list(tool_context: ToolContext) -> dict:
        apartment = apartment_of(tool_context)
        if apartment is None:
            return unavailable()
        found = await visitors.list_visitors(engine, apartment=apartment)
        return {
            "status": OK,
            "visitantes": [{"nome": v.name, "data": v.day.isoformat()} for v in found],
        }

    async def autorizar_visitante(nome: str, data: str, tool_context: ToolContext) -> dict:
        """Autoriza a entrada de um visitante do morador desta conversa em uma data.

        A autorização fica aguardando a confirmação do morador antes de gravar.

        Args:
            nome: nome do visitante, de 2 a 100 caracteres.
            data: data da visita, no formato AAAA-MM-DD.
        """
        return await safe(_authorize(nome, data, tool_context))

    async def listar_meus_visitantes(tool_context: ToolContext) -> dict:
        """Lista os visitantes autorizados do morador desta conversa.

        Não recebe parâmetros: o apartamento é conhecido pelo sistema.
        """
        return await safe(_list(tool_context))

    return [FunctionTool(autorizar_visitante), FunctionTool(listar_meus_visitantes)]
