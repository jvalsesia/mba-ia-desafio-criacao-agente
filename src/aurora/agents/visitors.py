from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm

VISITORS_NAME = "visitantes"

DESCRIPTION = (
    "Atende pedidos sobre visitantes: autorizar a entrada de um visitante e listar "
    "os visitantes autorizados do morador."
)

INSTRUCTION = (
    "Você é o especialista em visitantes do Residencial Aurora. "
    "As ferramentas de visitantes ainda não estão disponíveis. "
    "Informe isso ao morador, em português, e diga que ainda não consegue atender o pedido. "
    "Não invente reserva, visitante nem regra."
)


def build_visitors_agent(model: str | BaseLlm) -> LlmAgent:
    return LlmAgent(
        name=VISITORS_NAME,
        model=model,
        description=DESCRIPTION,
        instruction=INSTRUCTION,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
