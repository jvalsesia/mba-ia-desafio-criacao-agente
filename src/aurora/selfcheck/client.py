from dataclasses import dataclass
from typing import Any

import httpx

from aurora.selfcheck.checks import CheckFailed
from aurora.selfcheck.options import REQUEST_TIMEOUT


@dataclass
class Reply:
    status: int
    body: Any


def _reply(response: httpx.Response) -> Reply:
    try:
        body = response.json()
    except ValueError:
        body = response.text
    return Reply(status=response.status_code, body=body)


class AuroraClient:
    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base_url = base_url
        self._transport = transport
        self._client = httpx.AsyncClient(
            base_url=base_url, timeout=REQUEST_TIMEOUT, transport=transport
        )

    async def __aenter__(self) -> "AuroraClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self._client.aclose()

    async def create_session(self, apartment: str) -> Reply:
        return _reply(await self._client.post("/sessoes", json={"apartamento": apartment}))

    async def send(self, session_id: str, text: str) -> Reply:
        response = await self._client.post(f"/sessoes/{session_id}/mensagens", json={"texto": text})
        return _reply(response)

    async def confirm(self, session_id: str, confirmation_id: str, confirmed: bool) -> Reply:
        response = await self._client.post(
            f"/sessoes/{session_id}/confirmacoes",
            json={"id": confirmation_id, "confirmado": confirmed},
        )
        return _reply(response)

    async def events(self, session_id: str) -> Reply:
        return _reply(await self._client.get(f"/sessoes/{session_id}/eventos"))

    async def _list(self, apartment: str, resource: str) -> list[dict]:
        reply = _reply(await self._client.get(f"/apartamentos/{apartment}/{resource}"))
        if reply.status != 200 or not isinstance(reply.body, list):
            raise CheckFailed(
                f"GET /apartamentos/{apartment}/{resource} respondeu {reply.status}; esperado 200"
            )
        return reply.body

    async def reservations(self, apartment: str) -> list[dict]:
        return await self._list(apartment, "reservas")

    async def visitors(self, apartment: str) -> list[dict]:
        return await self._list(apartment, "visitantes")

    async def health(self) -> bool:
        try:
            return (await self._client.get("/health")).status_code == 200
        except httpx.HTTPError:
            return False

    def clone(self) -> "AuroraClient":
        return AuroraClient(self.base_url, transport=self._transport)

    async def reset(self) -> None:
        """Descarta as conexões abertas, por exemplo depois de reiniciar a API."""
        await self._client.aclose()
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=REQUEST_TIMEOUT, transport=self._transport
        )
