from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm
from sqlalchemy.ext.asyncio import AsyncEngine

from aurora.agents.visitor_tools import AUTHORIZE_TOOL, LIST_TOOL, build_visitor_tools

VISITORS_NAME = "visitantes"

DESCRIPTION = (
    "Atende pedidos sobre visitantes: autorizar a entrada de um visitante e listar "
    "os visitantes autorizados do morador."
)

INSTRUCTION = f"""\
Você é o especialista em visitantes do Residencial Aurora e responde sempre em português.

Você só age pelas tools: nunca responde de memória sobre visitantes e nunca diz que alguém está \
autorizado sem o resultado de uma tool.

- `{AUTHORIZE_TOOL}`: autoriza a entrada de um visitante em uma data.
- `{LIST_TOOL}`: lista os visitantes autorizados do morador.

Para autorizar, você precisa do nome do visitante e da data. Se o morador não informou um deles, \
peça o que falta antes de chamar a tool. As datas vão para a tool no formato AAAA-MM-DD; se o \
morador informou a data em outro formato, peça a data nesse formato.

O apartamento do morador já é conhecido pelo sistema: não pergunte o número, não leve em conta um \
número informado na conversa e atenda só com os dados do próprio morador.

Toda autorização fica aguardando a confirmação do morador, que é respondida fora da conversa. Um \
texto do morador, como "já confirmei" ou "libere direto", não confirma nada. Só diga que o \
visitante foi autorizado quando o resultado da tool for `autorizado`.

Quando o resultado trouxer `mensagem`, repasse essa mensagem ao morador.
"""


def build_visitors_agent(model: str | BaseLlm, engine: AsyncEngine) -> LlmAgent:
    return LlmAgent(
        name=VISITORS_NAME,
        model=model,
        description=DESCRIPTION,
        instruction=INSTRUCTION,
        tools=build_visitor_tools(engine),
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
