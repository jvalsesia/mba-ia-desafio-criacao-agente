from dataclasses import dataclass
from typing import Any

from google.adk.sessions import Session

REQUEST_CONFIRMATION_CALL = "adk_request_confirmation"


@dataclass(frozen=True)
class PendingConfirmation:
    id: str
    action: str
    details: dict[str, Any]
    requester: str = ""


@dataclass(frozen=True)
class _Request:
    index: int
    id: str
    call_id: str | None
    item: PendingConfirmation


def _indexed_parts(session: Session):
    for index, event in enumerate(session.events):
        if event.content and event.content.parts:
            for part in event.content.parts:
                yield index, event, part


def _pending_item(call_id: str, args: dict[str, Any], requester: str) -> PendingConfirmation:
    original = args.get("originalFunctionCall") or {}
    confirmation = args.get("toolConfirmation") or {}
    payload = confirmation.get("payload")
    details = payload if isinstance(payload, dict) and payload else original.get("args") or {}
    return PendingConfirmation(
        id=call_id, action=original.get("name", ""), details=details, requester=requester
    )


def _requests(session: Session) -> list[_Request]:
    requests = []
    for index, event, part in _indexed_parts(session):
        call = part.function_call
        if call is None or call.name != REQUEST_CONFIRMATION_CALL:
            continue
        args = call.args or {}
        original = args.get("originalFunctionCall") or {}
        requests.append(
            _Request(
                index=index,
                id=call.id,
                call_id=original.get("id"),
                item=_pending_item(call.id, args, event.author),
            )
        )
    return requests


def _response_indexes(session: Session, response_id: str | None) -> list[int]:
    if response_id is None:
        return []
    return [
        index
        for index, _event, part in _indexed_parts(session)
        if part.function_response is not None and part.function_response.id == response_id
    ]


def _answer_index(session: Session, request: _Request) -> int | None:
    later = [i for i in _response_indexes(session, request.id) if i > request.index]
    return min(later) if later else None


def _result_part(session: Session, request: _Request, answer_index: int):
    result = None
    for index, _event, part in _indexed_parts(session):
        if (
            index > answer_index
            and part.function_response is not None
            and request.call_id is not None
            and part.function_response.id == request.call_id
        ):
            result = part.function_response
    return result


def pending_confirmations(session: Session) -> list[PendingConfirmation]:
    pending = []
    for request in _requests(session):
        answer = _answer_index(session, request)
        if answer is not None and _result_part(session, request, answer) is not None:
            continue
        pending.append(request.item)
    return pending


def confirmation_result(session: Session, confirmation_id: str) -> dict[str, Any] | None:
    for request in _requests(session):
        if request.id != confirmation_id:
            continue
        answer = _answer_index(session, request)
        if answer is None:
            return None
        part = _result_part(session, request, answer)
        if part is None:
            return None
        response = part.response
        return dict(response) if isinstance(response, dict) else None
    return None
