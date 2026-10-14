import pytest
from google.adk.events.event import Event
from google.adk.sessions import Session
from google.genai import types

from aurora.conversation.pending import (
    PendingConfirmation,
    confirmation_result,
    pending_confirmations,
)

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


def _result(call_id, name="reservar_area", response=None, author="reservas"):
    return _event(
        author,
        "user",
        types.Part(
            function_response=types.FunctionResponse(
                id=call_id, name=name, response=response or {"status": "nao_confirmada"}
            )
        ),
    )


def _waiting(call_id, name="reservar_area", author="reservas"):
    return _result(call_id, name, {"status": "aguardando_confirmacao"}, author)


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


def test_answered_request_without_result_is_listed():
    result = pending_confirmations(_session([*_two_requests(), _answer("c1")]))
    assert [p.id for p in result] == ["c1", "c2"]


def test_resolved_request_is_not_listed():
    events = [*_two_requests(), _answer("c1"), _result("f1")]
    result = pending_confirmations(_session(events))
    assert result == [
        PendingConfirmation("c2", "autorizar_visitante", {"nome": "Joana"}, "reservas")
    ]


def test_waiting_result_before_answer_does_not_resolve():
    events = [_two_requests()[0], _waiting("f1"), _answer("c1")]
    assert [p.id for p in pending_confirmations(_session(events))] == ["c1"]


def test_result_of_another_call_does_not_resolve():
    events = [*_two_requests(), _answer("c1"), _result("f2", "autorizar_visitante")]
    assert [p.id for p in pending_confirmations(_session(events))] == ["c1", "c2"]


def test_second_answer_then_result_resolves():
    events = [_two_requests()[0], _answer("c1"), _answer("c1"), _result("f1")]
    assert pending_confirmations(_session(events)) == []


def test_pending_item_carries_requester():
    second = _request("c2", "f2", "autorizar_visitante", {"nome": "Joana"})
    second.author = "visitantes"
    result = pending_confirmations(_session([_two_requests()[0], second]))
    assert [p.requester for p in result] == ["reservas", "visitantes"]


def test_confirmation_result_returns_result_after_answer():
    events = [_two_requests()[0], _waiting("f1"), _answer("c1"), _result("f1")]
    assert confirmation_result(_session(events), "c1") == {"status": "nao_confirmada"}


@pytest.mark.parametrize(
    ("events", "confirmation_id"),
    [
        ([_two_requests()[0], _waiting("f1")], "c1"),
        ([_two_requests()[0], _waiting("f1"), _answer("c1")], "c1"),
        ([_two_requests()[0], _answer("c1"), _result("f1")], "desconhecido"),
    ],
    ids=["no-answer", "answer-without-result", "unknown-id"],
)
def test_confirmation_result_is_empty_without_answer_or_result(events, confirmation_id):
    assert confirmation_result(_session(events), confirmation_id) is None


def test_confirmation_result_returns_the_last_result():
    events = [
        _two_requests()[0],
        _answer("c1"),
        _result("f1", response={"status": "data_indisponivel"}),
        _result("f1", response={"status": "reservada"}),
    ]
    assert confirmation_result(_session(events), "c1") == {"status": "reservada"}


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
