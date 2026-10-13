"""Test doubles: a scripted ADK model standing in for Gemini, and a confirmation-gated tool."""

from collections.abc import AsyncGenerator

import httpx
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.adk.tools import FunctionTool
from google.genai import errors, types
from pydantic import Field


class ScriptedModel(BaseLlm):
    """Returns the next queued response on each call; queued exceptions are raised."""

    model: str = "scripted"
    queue: list = Field(default_factory=list)
    requests: list = Field(default_factory=list)

    @property
    def calls(self) -> int:
        return len(self.requests)

    def script(self, *entries) -> "ScriptedModel":
        self.queue.extend(entries)
        return self

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.requests.append(llm_request)
        if not self.queue:
            raise AssertionError("scripted model received a call with an empty script")
        entry = self.queue.pop(0)
        if isinstance(entry, BaseException):
            raise entry
        yield entry


def _response(part: types.Part) -> LlmResponse:
    return LlmResponse(content=types.Content(role="model", parts=[part]))


def text(value: str) -> LlmResponse:
    return _response(types.Part(text=value))


def empty_text() -> LlmResponse:
    return text("")


def tool_call(name: str, args: dict | None = None) -> LlmResponse:
    return _response(types.Part(function_call=types.FunctionCall(name=name, args=args or {})))


def transfer(agent_name: str) -> LlmResponse:
    return tool_call("transfer_to_agent", {"agent_name": agent_name})


def quota_error() -> errors.ClientError:
    body = {"error": {"code": 429, "message": "quota exceeded", "status": "RESOURCE_EXHAUSTED"}}
    return errors.ClientError(429, body)


def service_error() -> errors.ServerError:
    body = {"error": {"code": 503, "message": "unavailable", "status": "UNAVAILABLE"}}
    return errors.ServerError(503, body)


def connection_error() -> httpx.ConnectError:
    return httpx.ConnectError("connection failed")


class ConfirmationTool:
    """`acao_com_confirmacao`: asks for confirmation, writes nothing, records executions."""

    def __init__(self) -> None:
        self.executions: list[str] = []

        def acao_com_confirmacao(descricao: str) -> dict:
            """Executa uma ação de teste.

            Args:
                descricao: descrição da ação.
            """
            self.executions.append(descricao)
            return {"status": "executada"}

        self.tool = FunctionTool(acao_com_confirmacao, require_confirmation=True)
