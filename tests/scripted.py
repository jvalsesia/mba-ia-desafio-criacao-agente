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
        if callable(entry):
            entry = entry(llm_request)
        yield entry


def _response(part: types.Part) -> LlmResponse:
    return LlmResponse(content=types.Content(role="model", parts=[part]))


def text(value: str) -> LlmResponse:
    return _response(types.Part(text=value))


def empty_text() -> LlmResponse:
    return text("")


def tool_call(name: str, args: dict | None = None) -> LlmResponse:
    return _response(types.Part(function_call=types.FunctionCall(name=name, args=args or {})))


def tool_calls(*calls: tuple[str, dict]) -> LlmResponse:
    """One model response carrying several tool calls, from (name, args) pairs."""
    parts = [types.Part(function_call=types.FunctionCall(name=n, args=a)) for n, a in calls]
    return LlmResponse(content=types.Content(role="model", parts=parts))


def transfer(agent_name: str) -> LlmResponse:
    return tool_call("transfer_to_agent", {"agent_name": agent_name})


def relay_tool_message(llm_request: LlmRequest) -> LlmResponse:
    """Script entry: answer with the `mensagem` of the last tool result in the request."""
    for content in reversed(llm_request.contents):
        for part in reversed(content.parts or []):
            if part.function_response is not None:
                message = (part.function_response.response or {}).get("mensagem")
                return text(
                    message if isinstance(message, str) and message else "Pedido concluído."
                )
    return text("Pedido concluído.")


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
        self.fail_next = False

        def acao_com_confirmacao(descricao: str) -> dict:
            """Executa uma ação de teste.

            Args:
                descricao: descrição da ação.
            """
            if self.fail_next:
                self.fail_next = False
                raise RuntimeError("falha de teste")
            self.executions.append(descricao)
            return {"status": "executada"}

        self.tool = FunctionTool(acao_com_confirmacao, require_confirmation=True)
