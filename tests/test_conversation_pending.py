from google.adk.events.event import Event
from google.adk.sessions import Session
from google.genai import types

from aurora.conversation.pending import PendingConfirmation, pending_confirmations

PAYLOAD = {"area": "salao-de-festas", "data": "2030-04-20", "taxa": 150.0}


def _event(author, role, part):
    return Event(author=author, invocation_id="i", content=types.Content(role=role, parts=[part]))


def _request(conf_id, call_id, name, args, payload=None):
    confirmation = {"hint": "dica", "confirmed": False}
    if payload is not None:
        confirmation["payload"] = payload
    return _event(
        "reservas",
        "user",
        types.Part(
            function_call=types.FunctionCall(
                id=conf_id,
                name="adk_request_confirmation",
                args={
                    "originalFunctionCall": {"id": call_id, "name": name, "args": args},
                    "toolConfirmation": confirmation,
                },
            )
        ),
    )


def _answer(conf_id):
    return _event(
        "user",
        "user",
        types.Part(
            function_response=types.FunctionResponse(
                id=conf_id, name="adk_request_confirmation", response={"confirmed": False}
            )
        ),
    )


def _session(events):
    return Session(id="s", app_name="aurora", user_id="morador", events=events)


def _two_requests():
    return [
        _request("c1", "f1", "reservar_area", {"area": "salao-de-festas"}, PAYLOAD),
        _request("c2", "f2", "autorizar_visitante", {"nome": "Joana"}),
    ]


def test_no_events_returns_empty_list():
    assert pending_confirmations(_session([])) == []


def test_lists_pending_in_request_order():
    result = pending_confirmations(_session(_two_requests()))
    assert [p.id for p in result] == ["c1", "c2"]
    assert [p.action for p in result] == ["reservar_area", "autorizar_visitante"]


def test_details_use_payload_when_present():
    assert pending_confirmations(_session(_two_requests()))[0].details == PAYLOAD


def test_details_fall_back_to_call_arguments():
    assert pending_confirmations(_session(_two_requests()))[1].details == {"nome": "Joana"}


def test_answered_request_is_not_listed():
    result = pending_confirmations(_session([*_two_requests(), _answer("c1")]))
    assert result == [PendingConfirmation("c2", "autorizar_visitante", {"nome": "Joana"})]


def test_ignores_other_function_calls():
    call = _event(
        "reservas",
        "model",
        types.Part(function_call=types.FunctionCall(id="x", name="reservar_area", args={})),
    )
    text = _event("user", "user", types.Part(text="oi"))
    assert pending_confirmations(_session([text, call])) == []


def test_listing_does_not_change_the_session():
    session = _session(_two_requests())
    pending_confirmations(session)
    assert len(session.events) == 2
