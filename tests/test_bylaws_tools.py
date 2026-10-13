import pytest

import aurora.agents.bylaws_tools as bt
from aurora.agents.bylaws_document import load_bylaws


async def read(tools, ctx, numero):
    return await tools[bt.READ_TOOL](numero, ctx)


async def test_read_returns_the_chapter(bylaws_tools, bylaws, tool_context_for, empty_session):
    result = await read(bylaws_tools, tool_context_for(empty_session), 4)
    assert result["status"] == "ok"
    assert result["numero"] == 4
    assert result["titulo"] == "Piscina"
    assert result["texto"] == bylaws.chapter(4).text


async def test_read_result_has_one_chapter_only(bylaws_tools, tool_context_for, empty_session):
    result = await read(bylaws_tools, tool_context_for(empty_session), 4)
    assert "## Capítulo" not in result["texto"].split("\n", 1)[1]


async def test_third_read_is_refused(bylaws_tools, tool_context_for, empty_session):
    ctx = tool_context_for(empty_session)
    results = [await read(bylaws_tools, ctx, n) for n in (4, 8, 9)]
    assert [r["status"] for r in results] == ["ok", "ok", "limite_atingido"]
    assert "texto" not in results[2]
    assert results[2]["mensagem"] == bt.MSG_LIMIT_REACHED


async def test_repeated_chapter_counts(bylaws_tools, tool_context_for, empty_session):
    ctx = tool_context_for(empty_session)
    results = [await read(bylaws_tools, ctx, 4) for _ in range(3)]
    assert [r["status"] for r in results] == ["ok", "ok", "limite_atingido"]


async def test_invalid_number_returns_the_list(bylaws_tools, tool_context_for, empty_session):
    result = await read(bylaws_tools, tool_context_for(empty_session), 15)
    assert result["status"] == "capitulo_invalido"
    assert result["mensagem"] == bt.MSG_INVALID_CHAPTER
    assert len(result["capitulos"]) == 14
    assert all(set(c) == {"numero", "titulo"} for c in result["capitulos"])
    assert result["capitulos"][0] == {"numero": 1, "titulo": "Disposições gerais"}
    assert "texto" not in result


async def test_second_invalid_number_hits_the_limit(bylaws_tools, tool_context_for, empty_session):
    ctx = tool_context_for(empty_session)
    first = await read(bylaws_tools, ctx, 15)
    second = await read(bylaws_tools, ctx, 0)
    assert (first["status"], second["status"]) == ("capitulo_invalido", "limite_atingido")
    assert "capitulos" not in second


async def test_invalid_number_does_not_spend_the_budget(
    bylaws_tools, tool_context_for, empty_session
):
    ctx = tool_context_for(empty_session)
    results = [await read(bylaws_tools, ctx, n) for n in (99, 4, 8)]
    assert [r["status"] for r in results] == ["capitulo_invalido", "ok", "ok"]


async def test_read_after_limit_stays_refused(bylaws_tools, tool_context_for, empty_session):
    ctx = tool_context_for(empty_session)
    results = [await read(bylaws_tools, ctx, n) for n in (4, 8, 9, 4)]
    assert [r["status"] for r in results[2:]] == ["limite_atingido", "limite_atingido"]


@pytest.mark.parametrize("value", ["4", " 4 ", 4.0])
async def test_number_equivalents_are_accepted(
    bylaws_tools, tool_context_for, empty_session, value
):
    result = await read(bylaws_tools, tool_context_for(empty_session), value)
    assert result["status"] == "ok"
    assert result["numero"] == 4


@pytest.mark.parametrize("value", ["IV", "quatro", 4.5, True, None, 0, -1])
async def test_non_numbers_are_invalid(bylaws_tools, tool_context_for, empty_session, value):
    result = await read(bylaws_tools, tool_context_for(empty_session), value)
    assert result["status"] == "capitulo_invalido"


async def test_counters_live_in_temp_state(bylaws_tools, tool_context_for, empty_session):
    ctx = tool_context_for(empty_session)
    await read(bylaws_tools, ctx, 4)
    await read(bylaws_tools, ctx, 99)
    assert ctx.state.get(bt.READ_COUNT_KEY) == 1
    assert ctx.state.get(bt.INVALID_COUNT_KEY) == 1
    written = ctx.actions.state_delta
    assert written
    assert all(key.startswith("temp:") for key in written)


async def test_new_context_starts_from_zero(
    bylaws_tools, tool_context_for, empty_session, session_with_history
):
    first = tool_context_for(empty_session)
    await read(bylaws_tools, first, 4)
    await read(bylaws_tools, first, 8)
    second = tool_context_for(session_with_history)
    results = [await read(bylaws_tools, second, n) for n in (4, 8)]
    assert [r["status"] for r in results] == ["ok", "ok"]


def test_tool_declaration_has_only_numero(bylaws):
    (tool,) = bt.build_bylaws_tools(bylaws)
    schema = tool._get_declaration().parameters_json_schema
    assert list(schema["properties"]) == ["numero"]
    assert schema["properties"]["numero"]["type"] == "integer"
    assert schema["required"] == ["numero"]
    assert tool.name == bt.READ_TOOL


def test_bylaws_fixture_matches_the_loader(bylaws):
    assert len(bylaws.chapters) == len(load_bylaws().chapters)
