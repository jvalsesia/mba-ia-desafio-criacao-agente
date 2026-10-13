from google.adk.tools import FunctionTool, ToolContext

from aurora.agents.bylaws_document import Bylaws
from aurora.agents.tool_support import OK, refusal

READ_TOOL = "ler_capitulo"

MAX_CHAPTERS = 2
MAX_INVALID = 1

READ_COUNT_KEY = "temp:regulamento_capitulos_lidos"
INVALID_COUNT_KEY = "temp:regulamento_numeros_invalidos"

INVALID_CHAPTER = "capitulo_invalido"
LIMIT_REACHED = "limite_atingido"

MSG_INVALID_CHAPTER = "Capítulo inexistente. Escolha um número da lista."
MSG_LIMIT_REACHED = (
    "Limite de consultas atingido. Responda com o que já leu ou diga que não encontrou "
    "no regulamento."
)


def _as_chapter_number(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        text = value.strip()
        if text.isascii() and text.isdigit():
            return int(text)
    return None


def build_bylaws_tools(bylaws: Bylaws) -> list[FunctionTool]:
    async def ler_capitulo(numero: int, tool_context: ToolContext) -> dict:
        """Lê um capítulo do regulamento interno e devolve o título e o texto dele.

        Use o número do capítulo que aparece no índice. Cada pergunta permite ler poucos
        capítulos, então escolha o que trata da dúvida.

        Args:
            numero: número do capítulo no índice, a partir de 1.
        """
        state = tool_context.state
        chapter = None
        parsed = _as_chapter_number(numero)
        if parsed is not None:
            chapter = bylaws.chapter(parsed)
        if chapter is None:
            invalid = state.get(INVALID_COUNT_KEY, 0)
            if invalid >= MAX_INVALID:
                return refusal(LIMIT_REACHED, MSG_LIMIT_REACHED)
            state[INVALID_COUNT_KEY] = invalid + 1
            return {
                **refusal(INVALID_CHAPTER, MSG_INVALID_CHAPTER),
                "capitulos": [{"numero": c.number, "titulo": c.title} for c in bylaws.chapters],
            }
        delivered = state.get(READ_COUNT_KEY, 0)
        if delivered >= MAX_CHAPTERS:
            return refusal(LIMIT_REACHED, MSG_LIMIT_REACHED)
        state[READ_COUNT_KEY] = delivered + 1
        return {
            "status": OK,
            "numero": chapter.number,
            "titulo": chapter.title,
            "texto": chapter.text,
        }

    return [FunctionTool(ler_capitulo)]
