import logging
from typing import Any, override

import httpx
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import BaseLlm
from google.adk.tools import ToolContext
from google.adk.tools.agent_tool import AgentTool
from google.genai import errors, types

from aurora.agents.bylaws_document import Bylaws, render_index
from aurora.agents.bylaws_tools import (
    INVALID_CHAPTER,
    LIMIT_REACHED,
    MAX_CHAPTERS,
    READ_TOOL,
    build_bylaws_tools,
)

BYLAWS_NAME = "regulamento"

DESCRIPTION = "Responde dúvidas sobre as regras do condomínio, com base no regulamento interno."

MAX_ANSWER_CHARS = 800

MSG_NOT_FOUND = "Não encontrei isso no regulamento."
MSG_UNAVAILABLE = "Não consigo acessar o regulamento agora."

_SENTENCE_END = ".!?"

logger = logging.getLogger(__name__)

_INSTRUCTION = f"""\
Você é o especialista no regulamento interno do Residencial Aurora e responde sempre em português.

Você só responde com base no texto dos capítulos lidos pela tool `{READ_TOOL}` nesta pergunta: \
nunca responde de memória e nunca usa o índice como fonte da regra.

- Escolha o capítulo pelo índice abaixo e leia só o capítulo que trata da dúvida. Leia no máximo \
{MAX_CHAPTERS} capítulos por pergunta.
- A resposta é curta: a regra como está escrita e o artigo entre parênteses, no formato \
`(Art. 22)`. Não copie artigos que não respondem à dúvida.
- Se a dúvida não está no índice ou o capítulo lido não a responde, a resposta é exatamente \
`{MSG_NOT_FOUND}`
- Se a dúvida pode ser de mais de um assunto e não dá para escolher um capítulo, pergunte ao \
morador qual é o assunto, sem ler vários capítulos.
- Se a tool devolver `{INVALID_CHAPTER}`, escolha um número da lista e tente mais uma vez.
- Se a tool devolver `{LIMIT_REACHED}`, responda com o que já leu ou com `{MSG_NOT_FOUND}`

Índice do regulamento (capítulo, artigos e as palavras iniciais de cada artigo):

"""

_UNAVAILABLE_INSTRUCTION = (
    "Você é o especialista no regulamento interno do Residencial Aurora. "
    "O regulamento não está acessível. "
    f"Responda apenas: {MSG_UNAVAILABLE} Não invente nenhuma regra."
)


def build_instruction(bylaws: Bylaws) -> str:
    return _INSTRUCTION + render_index(bylaws)


def shorten(text: str, limit: int = MAX_ANSWER_CHARS) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    for i in range(limit - 1, -1, -1):
        if text[i] not in _SENTENCE_END:
            continue
        if text[i + 1] not in " \n":
            continue
        if text[: i + 1].endswith("Art."):
            continue
        return text[: i + 1]
    head = text[: limit - 1]
    cut = head.rsplit(" ", 1)[0] if " " in head else head
    return f"{cut.rstrip()}…"


def _unavailable_reply(callback_context: CallbackContext) -> types.Content:
    return types.Content(role="model", parts=[types.Part(text=MSG_UNAVAILABLE)])


def build_bylaws_agent(model: str | BaseLlm, bylaws: Bylaws | None) -> LlmAgent:
    if bylaws is None:
        return LlmAgent(
            name=BYLAWS_NAME,
            model=model,
            description=DESCRIPTION,
            instruction=_UNAVAILABLE_INSTRUCTION,
            tools=[],
            before_agent_callback=_unavailable_reply,
        )
    return LlmAgent(
        name=BYLAWS_NAME,
        model=model,
        description=DESCRIPTION,
        instruction=build_instruction(bylaws),
        tools=build_bylaws_tools(bylaws),
    )


class BylawsAgentTool(AgentTool):
    @override
    async def run_async(self, *, args: dict[str, Any], tool_context: ToolContext) -> Any:
        try:
            answer = await super().run_async(args=args, tool_context=tool_context)
        except (errors.APIError, httpx.TransportError) as error:
            logger.error("bylaws specialist model failed: %s", type(error).__name__)
            return MSG_UNAVAILABLE
        if not isinstance(answer, str) or not answer.strip():
            return MSG_NOT_FOUND
        return shorten(answer)


def build_bylaws_tool(model: str | BaseLlm, bylaws: Bylaws | None) -> BylawsAgentTool:
    return BylawsAgentTool(agent=build_bylaws_agent(model, bylaws))
