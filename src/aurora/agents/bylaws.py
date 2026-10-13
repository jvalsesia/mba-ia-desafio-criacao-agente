from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm

BYLAWS_NAME = "regulamento"

DESCRIPTION = "Responde dúvidas sobre as regras do condomínio, com base no regulamento interno."

INSTRUCTION = (
    "Você é o especialista no regulamento interno do Residencial Aurora. "
    "As ferramentas de consulta ao regulamento ainda não estão disponíveis. "
    "Informe isso ao morador, em português, e diga que ainda não consegue responder. "
    "Não invente reserva, visitante nem regra."
)


def build_bylaws_agent(model: str | BaseLlm) -> LlmAgent:
    return LlmAgent(name=BYLAWS_NAME, model=model, description=DESCRIPTION, instruction=INSTRUCTION)
