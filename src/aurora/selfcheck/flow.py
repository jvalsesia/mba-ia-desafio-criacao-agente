from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from aurora.config import DATA_DIR
from aurora.selfcheck.checks import CheckFailed, seed_codes
from aurora.selfcheck.client import AuroraClient, Reply
from aurora.selfcheck.options import FOLLOW_UP_TEXT, MAX_FOLLOW_UPS, SelfCheckOptions
from aurora.selfcheck.process import ApiProcess


@dataclass
class FlowState:
    s1: str | None = None
    s2: str | None = None
    s3: str | None = None
    s4: str | None = None
    approved_hall_id: str | None = None
    denied_hall_id: str | None = None
    s1_event_count: int | None = None
    hall_codes: dict[str, str] = field(default_factory=dict)


@dataclass
class FlowContext:
    client: AuroraClient
    api: ApiProcess
    options: SelfCheckOptions
    state: FlowState
    bylaws_lines: list[tuple[str, str]]
    seed_codes: set[str]
    data_dir: Path = DATA_DIR

    @classmethod
    def build(
        cls,
        client: AuroraClient,
        api: ApiProcess,
        options: SelfCheckOptions,
        bylaws_lines: list[tuple[str, str]],
    ) -> "FlowContext":
        return cls(
            client=client,
            api=api,
            options=options,
            state=FlowState(),
            bylaws_lines=bylaws_lines,
            seed_codes=seed_codes(DATA_DIR / "reservas.json"),
        )


@dataclass
class Exchange:
    replies: list[Reply] = field(default_factory=list)

    def texts(self) -> list[str]:
        return [str(r.body.get("resposta", "")) for r in self.replies if isinstance(r.body, dict)]

    def pending(self) -> list[dict]:
        items: list[dict] = []
        for reply in self.replies:
            if isinstance(reply.body, dict):
                items.extend(reply.body.get("confirmacoes_pendentes") or [])
        return items


Until = Callable[[Exchange], Awaitable[bool]]


async def converse(
    ctx: FlowContext, session_id: str, text: str, until: Until | None = None
) -> Exchange:
    exchange = Exchange()
    message = text
    follow_ups = 0
    while True:
        reply = await ctx.client.send(session_id, message)
        if reply.status != 200:
            raise CheckFailed(
                f"POST /sessoes/{session_id}/mensagens respondeu {reply.status}; esperado 200"
            )
        exchange.replies.append(reply)
        if until is None or await until(exchange) or follow_ups >= MAX_FOLLOW_UPS:
            return exchange
        follow_ups += 1
        message = FOLLOW_UP_TEXT
