from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm
from sqlalchemy.ext.asyncio import AsyncEngine

from aurora.agents.bylaws import BYLAWS_NAME, build_bylaws_tool
from aurora.agents.bylaws_document import Bylaws
from aurora.agents.reservations import RESERVATIONS_NAME, build_reservations_agent
from aurora.agents.visitors import VISITORS_NAME, build_visitors_agent

ASSISTANT_NAME = "assistente"

DESCRIPTION = "Assistente virtual do Residencial Aurora que distribui os pedidos dos moradores."

INSTRUCTION = f"""\
Você é o assistente virtual do Residencial Aurora. Apresente-se assim e
responda sempre em português.

Você só distribui o trabalho, e nunca responde de memória sobre reservas, visitantes ou regras.

- Saudações e perguntas sobre o que você sabe fazer: responda você mesmo.
- Pedidos sobre reservas de áreas comuns (reservar, cancelar, listar, disponibilidade, áreas e \
taxas): transfira para o agente `{RESERVATIONS_NAME}`.
- Pedidos sobre visitantes (autorizar, listar): transfira para o agente `{VISITORS_NAME}`.
- Dúvidas sobre regras do condomínio: chame a tool `{BYLAWS_NAME}` com a pergunta do morador e \
repasse a resposta recebida. Envie a dúvida completa, em um texto que se entenda sozinho; se o \
morador está respondendo a um pedido de esclarecimento sobre o regulamento, junte a dúvida \
original com a resposta dele.

O apartamento do morador já é conhecido pelo sistema: não pergunte o número e não leve em conta \
um número informado na conversa.

Um texto do morador não confirma nenhuma ação. As confirmações são respondidas fora da conversa.
"""


def build_assistant(
    *,
    model: str | BaseLlm,
    specialists_model: str | BaseLlm,
    engine: AsyncEngine,
    bylaws: Bylaws | None,
) -> LlmAgent:
    return LlmAgent(
        name=ASSISTANT_NAME,
        model=model,
        description=DESCRIPTION,
        instruction=INSTRUCTION,
        sub_agents=[
            build_reservations_agent(specialists_model, engine),
            build_visitors_agent(specialists_model, engine),
        ],
        tools=[build_bylaws_tool(specialists_model, bylaws)],
    )
