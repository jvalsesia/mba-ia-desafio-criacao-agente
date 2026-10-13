import json
from pathlib import Path

import pytest

from aurora.agents.bylaws_document import load_bylaws, render_index
from aurora.config import DATA_DIR
from tests import scripted as sc
from tests.conftest import build_scripted_runner
from tests.test_reservations_conversation import content_of, events_of, results_of, say

FIXTURES = Path(__file__).parent / "fixtures"
POOL_QUESTION = "Até que horas a piscina funciona aos domingos?"
POOL_ANSWER = "Aos domingos e feriados, a piscina funciona das 9h às 20h (Art. 22)."
NOT_FOUND = "Não encontrei isso no regulamento."
UNAVAILABLE = "Não consigo acessar o regulamento agora."
LIMIT_MESSAGE = (
    "Limite de consultas atingido. Responda com o que já leu ou diga que não encontrou "
    "no regulamento."
)
UNIQUE_PHRASES = (
    "coleira refletiva cor de mostarda",
    "plástico bolha lilás",
    "lona xadrez vermelha",
    "dez quilômetros por hora",
)


def source_lines():
    return (DATA_DIR / "regulamento.md").read_text(encoding="utf-8").splitlines()


def chapter_text(number):
    return load_bylaws(DATA_DIR).chapter(number).text


def ask(scripted, request=POOL_QUESTION, *main_end):
    scripted.main.script(sc.tool_call("regulamento", {"request": request}), *main_end)


def script_pool(scripted):
    ask(scripted, POOL_QUESTION, sc.text(POOL_ANSWER))
    scripted.specialists.script(sc.tool_call("ler_capitulo", {"numero": 4}), sc.text(POOL_ANSWER))


def parts_of(request):
    return [p for c in request.contents for p in (c.parts or [])]


def read_results(model):
    """Every `ler_capitulo` result the model received, in order of first appearance."""
    found = []
    for request in model.requests:
        for part in parts_of(request):
            response = part.function_response
            if response and response.name == "ler_capitulo":
                if response.response not in found:
                    found.append(response.response)
    return found


def received(model) -> str:
    chunks = []
    for request in model.requests:
        chunks.append(str(request.config.system_instruction))
        for part in parts_of(request):
            if part.text:
                chunks.append(part.text)
            if part.function_call:
                chunks.append(json.dumps(dict(part.function_call.args or {}), ensure_ascii=False))
            if part.function_response:
                chunks.append(json.dumps(part.function_response.response, ensure_ascii=False))
    return "\n".join(chunks)


def instruction_of(model, index=0) -> str:
    return str(model.requests[index].config.system_instruction)


def runner_over(client, scripted, folder):
    client.app.state.runner = build_scripted_runner(
        scripted,
        client.app.state.session_service,
        client.app.state.engine,
        data_dir=FIXTURES / folder,
    )


def bylaws_results(events):
    return [r["result"] for r in results_of(events, "regulamento")]


# --- answers -----------------------------------------------------------------------------------


async def test_pool_question_returns_the_closing_time(conversation_client, scripted, empty_session):
    script_pool(scripted)
    r = await say(conversation_client, empty_session, POOL_QUESTION)
    assert r.status_code == 200
    assert r.json() == {"resposta": POOL_ANSWER, "confirmacoes_pendentes": []}
    assert "20h" in r.json()["resposta"]


async def test_specialist_receives_the_requested_chapter(
    conversation_client, scripted, empty_session
):
    script_pool(scripted)
    await say(conversation_client, empty_session, POOL_QUESTION)
    [result] = read_results(scripted.specialists)
    assert result["status"] == "ok" and result["numero"] == 4 and result["titulo"] == "Piscina"
    assert result["texto"] == chapter_text(4)
    assert result["texto"].startswith("## Capítulo IV: Piscina")
    assert "II. Aos domingos e feriados, a piscina funciona das 9h às 20h." in result["texto"]
    assert "## Capítulo V" not in result["texto"]
    assert not any(p in result["texto"] for p in UNIQUE_PHRASES)


async def test_resident_session_has_four_events(conversation_client, scripted, empty_session):
    script_pool(scripted)
    await say(conversation_client, empty_session, POOL_QUESTION)
    events = await events_of(conversation_client, empty_session)
    assert len(events) == 4
    call = events[1]["content"]["parts"][0]["functionCall"]
    assert call["name"] == "regulamento" and call["args"] == {"request": POOL_QUESTION}
    assert bylaws_results(events) == [POOL_ANSWER]
    assert all(e["author"] != "regulamento" for e in events)
    assert "ler_capitulo" not in json.dumps(events)


async def test_resident_state_is_unchanged(conversation_client, scripted, empty_session):
    script_pool(scripted)
    await say(conversation_client, empty_session, POOL_QUESTION)
    session = await conversation_client.app.state.session_service.get_session(
        app_name=empty_session.app_name, user_id=empty_session.user_id, session_id=empty_session.id
    )
    assert set(session.state) == {"apartamento"}


async def test_specialist_instruction_carries_the_index(
    conversation_client, scripted, empty_session
):
    script_pool(scripted)
    await say(conversation_client, empty_session, POOL_QUESTION)
    instruction = instruction_of(scripted.specialists)
    index = render_index(load_bylaws(DATA_DIR))
    assert index in instruction
    assert "4. Piscina (Art. 21 a 28)" in instruction
    assert "14. Disposições finais (Art. 93 a 96)" in instruction
    assert "Art. 22: A piscina observa os seguintes períodos de uso:" in instruction
    assert all(f"Art. {n}:" in instruction for n in range(1, 97))
    assert NOT_FOUND in instruction and "ler_capitulo" in instruction
    assert len(instruction) < 12000
    assert "## Capítulo" not in instruction
    assert not any(p in instruction for p in UNIQUE_PHRASES)
    assert not any(len(line) >= 40 and line in instruction for line in source_lines())


async def test_main_agent_receives_no_bylaws_text(conversation_client, scripted, empty_session):
    script_pool(scripted)
    await say(conversation_client, empty_session, POOL_QUESTION)
    instruction = instruction_of(scripted.main)
    assert not any(len(line) >= 40 and line in instruction for line in source_lines())
    assert not any(
        line[3:] in instruction for line in source_lines() if line.startswith("## Capítulo")
    )
    assert "Art." not in instruction
    assert "## Capítulo" not in received(scripted.main)
    assert "ler_capitulo" not in received(scripted.main)


# --- limits --------------------------------------------------------------------------------------


async def test_third_chapter_is_refused_in_the_run(conversation_client, scripted, empty_session):
    ask(scripted, "Posso levar meu cachorro na mudança?", sc.text(NOT_FOUND))
    scripted.specialists.script(
        sc.tool_call("ler_capitulo", {"numero": 4}),
        sc.tool_call("ler_capitulo", {"numero": 8}),
        sc.tool_call("ler_capitulo", {"numero": 9}),
        sc.text(NOT_FOUND),
    )
    r = await say(conversation_client, empty_session, "Posso levar meu cachorro na mudança?")
    results = read_results(scripted.specialists)
    assert r.status_code == 200
    assert [x["status"] for x in results] == ["ok", "ok", "limite_atingido"]
    assert results[2] == {"status": "limite_atingido", "mensagem": LIMIT_MESSAGE}
    assert "plástico bolha lilás" not in received(scripted.specialists)


async def test_three_chapters_in_one_step(conversation_client, scripted, empty_session):
    ask(scripted, "Quais são as regras gerais?", sc.text(NOT_FOUND))
    scripted.specialists.script(
        sc.tool_calls(*[("ler_capitulo", {"numero": n}) for n in (9, 10, 11)]),
        sc.text(NOT_FOUND),
    )
    await say(conversation_client, empty_session, "Quais são as regras gerais?")
    statuses = sorted(x["status"] for x in read_results(scripted.specialists))
    assert statuses == ["limite_atingido", "ok", "ok"]
    got = received(scripted.specialists)
    assert sum(p in got for p in UNIQUE_PHRASES[1:]) <= 2


async def test_limit_is_per_question(conversation_client, scripted, empty_session):
    ask(scripted, "Posso levar meu cachorro à piscina?", sc.text(NOT_FOUND))
    scripted.main.script(
        sc.tool_call("regulamento", {"request": "Qual é a velocidade máxima na garagem?"}),
        sc.text("A velocidade máxima na garagem é de dez quilômetros por hora (Art. 78)."),
    )
    scripted.specialists.script(
        sc.tool_call("ler_capitulo", {"numero": 4}),
        sc.tool_call("ler_capitulo", {"numero": 8}),
        sc.text(NOT_FOUND),
        sc.tool_call("ler_capitulo", {"numero": 11}),
        sc.text("A velocidade máxima na garagem é de dez quilômetros por hora (Art. 78)."),
    )
    await say(conversation_client, empty_session, "Posso levar meu cachorro à piscina?")
    r = await say(conversation_client, empty_session, "Qual é a velocidade máxima na garagem?")
    assert r.json()["resposta"].startswith("A velocidade máxima")
    last = scripted.specialists.requests[-1]
    [response] = [
        p.function_response.response
        for p in parts_of(last)
        if p.function_response and p.function_response.name == "ler_capitulo"
    ]
    assert response["status"] == "ok" and response["numero"] == 11


async def test_invalid_chapter_then_retry(conversation_client, scripted, empty_session):
    script_pool(scripted)
    scripted.specialists.queue.clear()
    scripted.specialists.script(
        sc.tool_call("ler_capitulo", {"numero": 15}),
        sc.tool_call("ler_capitulo", {"numero": 4}),
        sc.text(POOL_ANSWER),
    )
    await say(conversation_client, empty_session, POOL_QUESTION)
    first, second = read_results(scripted.specialists)
    assert first["status"] == "capitulo_invalido" and len(first["capitulos"]) == 14
    assert first["capitulos"][0] == {"numero": 1, "titulo": "Disposições gerais"}
    assert "texto" not in first
    assert second["status"] == "ok" and second["numero"] == 4


async def test_second_invalid_chapter_hits_the_limit(conversation_client, scripted, empty_session):
    ask(scripted, POOL_QUESTION, sc.text(NOT_FOUND))
    scripted.specialists.script(
        sc.tool_call("ler_capitulo", {"numero": 15}),
        sc.tool_call("ler_capitulo", {"numero": 0}),
        sc.text(NOT_FOUND),
    )
    r = await say(conversation_client, empty_session, POOL_QUESTION)
    first, second = read_results(scripted.specialists)
    assert r.status_code == 200
    assert (first["status"], second["status"]) == ("capitulo_invalido", "limite_atingido")
    assert "capitulos" not in second


async def test_invalid_does_not_spend_the_chapter_budget(
    conversation_client, scripted, empty_session
):
    ask(scripted, POOL_QUESTION, sc.text(POOL_ANSWER))
    scripted.specialists.script(
        *[sc.tool_call("ler_capitulo", {"numero": n}) for n in (99, 4, 5, 6)],
        sc.text(POOL_ANSWER),
    )
    await say(conversation_client, empty_session, POOL_QUESTION)
    statuses = [x["status"] for x in read_results(scripted.specialists)]
    assert statuses == ["capitulo_invalido", "ok", "ok", "limite_atingido"]


@pytest.mark.parametrize("value", ["IV", "quatro", 4.5, True, 0, -1])
async def test_non_number_through_the_run(conversation_client, scripted, empty_session, value):
    ask(scripted, POOL_QUESTION, sc.text(NOT_FOUND))
    scripted.specialists.script(sc.tool_call("ler_capitulo", {"numero": value}), sc.text(NOT_FOUND))
    r = await say(conversation_client, empty_session, POOL_QUESTION)
    [result] = read_results(scripted.specialists)
    assert r.status_code == 200
    assert result["status"] == "capitulo_invalido" and "texto" not in result


@pytest.mark.parametrize("value", ["4", 4.0])
async def test_digit_text_is_accepted_through_the_run(
    conversation_client, scripted, empty_session, value
):
    ask(scripted, POOL_QUESTION, sc.text(POOL_ANSWER))
    scripted.specialists.script(
        sc.tool_call("ler_capitulo", {"numero": value}), sc.text(POOL_ANSWER)
    )
    await say(conversation_client, empty_session, POOL_QUESTION)
    [result] = read_results(scripted.specialists)
    assert result["status"] == "ok" and result["numero"] == 4


async def test_missing_numero_is_not_executed(conversation_client, scripted, empty_session):
    ask(scripted, POOL_QUESTION, sc.text(NOT_FOUND))
    scripted.specialists.script(
        sc.tool_call("ler_capitulo", {}),
        sc.tool_call("ler_capitulo", {"numero": 4}),
        sc.tool_call("ler_capitulo", {"numero": 8}),
        sc.text(NOT_FOUND),
    )
    await say(conversation_client, empty_session, POOL_QUESTION)
    responses = [
        p.function_response.response
        for p in parts_of(scripted.specialists.requests[-1])
        if p.function_response
    ]
    assert "error" in responses[0] and "numero" in json.dumps(responses[0])
    assert [r["status"] for r in responses[1:]] == ["ok", "ok"]


# --- not found, clarification, short answers ---------------------------------------------------


async def test_not_found_answer_reaches_the_resident(conversation_client, scripted, empty_session):
    ask(scripted, "Posso instalar painel solar na sacada?", sc.text(NOT_FOUND))
    scripted.specialists.script(sc.text(NOT_FOUND))
    r = await say(conversation_client, empty_session, "Posso instalar painel solar na sacada?")
    events = await events_of(conversation_client, empty_session)
    assert r.status_code == 200 and r.json()["resposta"] == NOT_FOUND
    assert bylaws_results(events) == [NOT_FOUND]
    assert scripted.specialists.calls == 1
    assert "Art." not in content_of(events)


async def test_empty_answer_becomes_not_found(conversation_client, scripted, empty_session):
    ask(scripted, "Posso instalar painel solar na sacada?", sc.text(NOT_FOUND))
    scripted.specialists.script(sc.empty_text())
    r = await say(conversation_client, empty_session, "Posso instalar painel solar na sacada?")
    events = await events_of(conversation_client, empty_session)
    assert r.status_code == 200 and r.json()["resposta"] == NOT_FOUND
    assert bylaws_results(events) == [NOT_FOUND]


async def test_clarifying_question_loads_no_chapter(conversation_client, scripted, empty_session):
    question = (
        "Você quer saber o horário de qual área: piscina, academia, brinquedoteca ou playground?"
    )
    ask(scripted, "Qual é o horário?", sc.text(question))
    scripted.specialists.script(sc.text(question))
    r = await say(conversation_client, empty_session, "Qual é o horário?")
    events = await events_of(conversation_client, empty_session)
    assert r.json()["resposta"] == question
    assert scripted.specialists.calls == 1
    assert read_results(scripted.specialists) == []
    assert "## Capítulo" not in content_of(events)


async def test_clarified_question_starts_a_new_question(
    conversation_client, scripted, empty_session
):
    question = (
        "Você quer saber o horário de qual área: piscina, academia, brinquedoteca ou playground?"
    )
    full = "Qual é o horário de funcionamento da piscina aos domingos?"
    scripted.main.script(
        sc.tool_call("regulamento", {"request": "Qual é o horário?"}),
        sc.text(question),
        sc.tool_call("regulamento", {"request": full}),
        sc.text(POOL_ANSWER),
    )
    scripted.specialists.script(
        sc.text(question), sc.tool_call("ler_capitulo", {"numero": 4}), sc.text(POOL_ANSWER)
    )
    await say(conversation_client, empty_session, "Qual é o horário?")
    r = await say(conversation_client, empty_session, "Da piscina, aos domingos.")
    first_of_second = scripted.specialists.requests[1]
    assert r.json()["resposta"] == POOL_ANSWER
    assert [p.text for p in parts_of(first_of_second)] == [full]
    assert read_results(scripted.specialists)[0]["numero"] == 4


async def test_each_question_starts_a_fresh_session(conversation_client, scripted, empty_session):
    ask(scripted, "Primeira dúvida?", sc.text(NOT_FOUND))
    scripted.main.script(
        sc.tool_call("regulamento", {"request": "Segunda dúvida?"}), sc.text(NOT_FOUND)
    )
    scripted.specialists.script(sc.text(NOT_FOUND), sc.text(NOT_FOUND))
    await say(conversation_client, empty_session, "Primeira dúvida?")
    await say(conversation_client, empty_session, "Segunda dúvida?")
    assert [p.text for p in parts_of(scripted.specialists.requests[1])] == ["Segunda dúvida?"]


async def test_long_answer_is_cut(conversation_client, scripted, empty_session):
    ask(scripted, "Quais são as regras para animais?", sc.text("Há várias regras. Qual?"))
    scripted.specialists.script(
        sc.tool_call("ler_capitulo", {"numero": 8}), sc.text(chapter_text(8))
    )
    await say(conversation_client, empty_session, "Quais são as regras para animais?")
    events = await events_of(conversation_client, empty_session)
    [result] = bylaws_results(events)
    assert len(result) <= 800 and result.endswith(".")
    assert chapter_text(8).startswith(result)
    assert "coleira refletiva cor de mostarda" not in content_of(events)


async def test_earlier_tool_calls_stay_in_the_session(
    conversation_client, scripted, session_with_history
):
    ask(scripted, POOL_QUESTION, sc.text(POOL_ANSWER))
    scripted.specialists.script(
        sc.tool_call("ler_capitulo", {"numero": 4}),
        sc.tool_call("ler_capitulo", {"numero": 8}),
        sc.text(POOL_ANSWER),
    )
    before = await events_of(conversation_client, session_with_history)
    await say(conversation_client, session_with_history, POOL_QUESTION)
    events = await events_of(conversation_client, session_with_history)
    assert len(events) == 8
    assert events[:4] == before
    content = content_of(events)
    assert "coleira refletiva cor de mostarda" not in content
    assert not any(len(row) >= 40 and row in content for row in chapter_text(8).splitlines())


# --- unavailable bylaws ---------------------------------------------------------------------------


@pytest.mark.parametrize("folder", ["bylaws_missing", "bylaws_unreadable", "bylaws_no_chapters"])
async def test_unusable_file_answers_without_the_model(client, scripted, empty_session, folder):
    runner_over(client, scripted, folder)
    ask(scripted, POOL_QUESTION, sc.text(UNAVAILABLE))
    r = await say(client, empty_session, POOL_QUESTION)
    events = await events_of(client, empty_session)
    assert r.status_code == 200
    assert r.json() == {"resposta": UNAVAILABLE, "confirmacoes_pendentes": []}
    assert bylaws_results(events) == [UNAVAILABLE]
    assert scripted.specialists.calls == 0


async def test_other_requests_work_without_the_file(client, scripted, empty_session):
    runner_over(client, scripted, "bylaws_missing")
    scripted.main.script(sc.text("Olá! Sou o assistente do Residencial Aurora."))
    r = await say(client, empty_session, "Olá")
    assert r.status_code == 200
    assert r.json()["resposta"] == "Olá! Sou o assistente do Residencial Aurora."


@pytest.mark.parametrize("failure", [sc.quota_error, sc.service_error, sc.connection_error])
async def test_specialist_model_failure_returns_fixed_result(
    conversation_client, scripted, empty_session, failure
):
    ask(scripted, POOL_QUESTION, sc.text(UNAVAILABLE))
    scripted.specialists.script(failure())
    r = await say(conversation_client, empty_session, POOL_QUESTION)
    events = await events_of(conversation_client, empty_session)
    assert r.status_code == 200 and r.json()["resposta"] == UNAVAILABLE
    assert bylaws_results(events) == [UNAVAILABLE]
    calls = {
        p["functionCall"]["id"]
        for e in events
        for p in e["content"]["parts"]
        if "functionCall" in p
    }
    done = {
        p["functionResponse"]["id"]
        for e in events
        for p in e["content"]["parts"]
        if "functionResponse" in p
    }
    assert calls <= done


async def test_session_works_after_specialist_failure(conversation_client, scripted, empty_session):
    ask(scripted, POOL_QUESTION, sc.text(UNAVAILABLE), sc.text("Olá! Como posso ajudar?"))
    scripted.specialists.script(sc.quota_error())
    await say(conversation_client, empty_session, POOL_QUESTION)
    r = await say(conversation_client, empty_session, "Olá")
    assert r.status_code == 200 and r.json()["resposta"] == "Olá! Como posso ajudar?"
    parts = parts_of(scripted.main.requests[-1])
    names = [
        ("call" if p.function_call else "result", (p.function_call or p.function_response).name)
        for p in parts
        if p.function_call or p.function_response
    ]
    assert names == [("call", "regulamento"), ("result", "regulamento")]


async def test_main_model_failure_still_returns_503(conversation_client, scripted, empty_session):
    ask(scripted, POOL_QUESTION, sc.quota_error())
    scripted.specialists.script(sc.quota_error())
    r = await say(conversation_client, empty_session, POOL_QUESTION)
    events = await events_of(conversation_client, empty_session)
    assert r.status_code == 503
    assert r.json()["detail"] == "Assistente temporariamente indisponível. Tente novamente."
    assert bylaws_results(events) == [UNAVAILABLE]
