from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm

RESERVATIONS_NAME = "reservas"

DESCRIPTION = (
    "Atende pedidos sobre reservas de áreas comuns: reservar, cancelar, listar as reservas "
    "do morador, consultar disponibilidade, áreas e taxas."
)

INSTRUCTION = (
    "Você é o especialista em reservas de áreas comuns do Residencial Aurora. "
    "As ferramentas de reservas ainda não estão disponíveis. "
    "Informe isso ao morador, em português, e diga que ainda não consegue atender o pedido. "
    "Não invente reserva, visitante nem regra."
)


def build_reservations_agent(model: str | BaseLlm) -> LlmAgent:
    return LlmAgent(
        name=RESERVATIONS_NAME,
        model=model,
        description=DESCRIPTION,
        instruction=INSTRUCTION,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
