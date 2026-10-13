from dataclasses import dataclass
from typing import Any

from google.adk.sessions import Session

REQUEST_CONFIRMATION_CALL = "adk_request_confirmation"


@dataclass(frozen=True)
class PendingConfirmation:
    id: str
    action: str
    details: dict[str, Any]


def _parts(session: Session):
    for event in session.events:
        if event.content and event.content.parts:
            yield from event.content.parts


def _pending_item(call_id: str, args: dict[str, Any]) -> PendingConfirmation:
    original = args.get("originalFunctionCall") or {}
    confirmation = args.get("toolConfirmation") or {}
    payload = confirmation.get("payload")
    details = payload if isinstance(payload, dict) and payload else original.get("args") or {}
    return PendingConfirmation(id=call_id, action=original.get("name", ""), details=details)


def pending_confirmations(session: Session) -> list[PendingConfirmation]:
    parts = list(_parts(session))
    answered = {p.function_response.id for p in parts if p.function_response is not None}
    return [
        _pending_item(p.function_call.id, p.function_call.args or {})
        for p in parts
        if p.function_call is not None
        and p.function_call.name == REQUEST_CONFIRMATION_CALL
        and p.function_call.id not in answered
    ]
