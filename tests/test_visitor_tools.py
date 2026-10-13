import pytest
from sqlalchemy import text

import aurora.agents.visitor_tools as vt

SEED = [("302", "Marina Duarte", "2030-03-16"), ("201", "Paulo Nogueira", "2030-03-23")]
FAILURE_MESSAGE = "Não consegui concluir o pedido agora. Tente novamente em instantes."
JOANA = {"nome": "Joana Ribeiro", "data": "2030-04-21"}


async def rows(engine, where="true"):
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT apartment, name, day::text AS day FROM visitors "
                f"WHERE {where} ORDER BY apartment, day, name"
            )
        )
        return [tuple(r) for r in result]


async def seed_only(engine):
    return sorted(await rows(engine), key=lambda r: r[0], reverse=True) == sorted(
        SEED, key=lambda r: r[0], reverse=True
    )


def requested(ctx):
    return ctx.actions.requested_tool_confirmations


async def authorize(tools, ctx, nome, data):
    return await tools[vt.AUTHORIZE_TOOL](nome, data, ctx)


# --- authorize -------------------------------------------------------------------------------


async def test_authorize_requests_confirmation(
    visitor_tools, tool_context_for, empty_session, engine
):
    ctx = tool_context_for(empty_session)
    result = await authorize(visitor_tools, ctx, **JOANA)
    assert result["status"] == "aguardando_confirmacao"
    request = requested(ctx)["fc-tool"]
    assert request.hint == "Liberação de acesso"
    assert request.payload == JOANA
    assert await rows(engine, "apartment = '101'") == []


async def test_authorize_marks_result_as_final(visitor_tools, tool_context_for, empty_session):
    ctx = tool_context_for(empty_session)
    await authorize(visitor_tools, ctx, **JOANA)
    assert ctx.actions.skip_summarization is True


async def test_authorize_normalizes_name_in_request(visitor_tools, tool_context_for, empty_session):
    ctx = tool_context_for(empty_session)
    await authorize(visitor_tools, ctx, "  Joana   Ribeiro ", "2030-04-21")
    assert requested(ctx)["fc-tool"].payload == JOANA


async def test_authorize_approved_creates_visitor(
    visitor_tools, tool_context_for, empty_session, engine
):
    ctx = tool_context_for(empty_session, confirmed=True)
    result = await authorize(visitor_tools, ctx, **JOANA)
    assert result == {"status": "autorizado", **JOANA}
    assert requested(ctx) == {}
    assert await rows(engine, "apartment = '101'") == [("101", "Joana Ribeiro", "2030-04-21")]


async def test_authorize_denied_writes_nothing(
    visitor_tools, tool_context_for, empty_session, engine
):
    ctx = tool_context_for(empty_session, confirmed=False)
    result = await authorize(visitor_tools, ctx, **JOANA)
    assert result["status"] == "nao_confirmada"
    assert result["mensagem"] == "A autorização não foi confirmada. Nada foi alterado."
    assert requested(ctx) == {}
    assert await seed_only(engine)


async def approve(tools, tool_context_for, session, nome="Joana Ribeiro", data="2030-04-21"):
    return await authorize(tools, tool_context_for(session, confirmed=True), nome, data)


async def test_authorize_duplicate_is_refused_before_confirmation(
    visitor_tools, tool_context_for, empty_session, engine
):
    await approve(visitor_tools, tool_context_for, empty_session)
    ctx = tool_context_for(empty_session)
    result = await authorize(visitor_tools, ctx, **JOANA)
    assert result == {
        "status": "ja_autorizado",
        "mensagem": "Esse visitante já está autorizado nessa data.",
    }
    assert requested(ctx) == {}
    assert len(await rows(engine, "apartment = '101'")) == 1


async def test_authorize_duplicate_on_approval(
    visitor_tools, tool_context_for, empty_session, engine
):
    await approve(visitor_tools, tool_context_for, empty_session)
    result = await approve(visitor_tools, tool_context_for, empty_session)
    assert result["status"] == "ja_autorizado"
    assert len(await rows(engine, "apartment = '101'")) == 1


async def test_authorize_duplicate_ignores_case_and_spacing(
    visitor_tools, tool_context_for, empty_session, engine
):
    await approve(visitor_tools, tool_context_for, empty_session)
    ctx = tool_context_for(empty_session)
    first = await authorize(visitor_tools, ctx, " joana  RIBEIRO ", "2030-04-21")
    second = await approve(visitor_tools, tool_context_for, empty_session, " joana  RIBEIRO ")
    assert first["status"] == second["status"] == "ja_autorizado"
    assert requested(ctx) == {}
    assert len(await rows(engine, "apartment = '101'")) == 1


async def test_authorize_same_name_on_another_date(visitor_tools, tool_context_for, empty_session):
    await approve(visitor_tools, tool_context_for, empty_session)
    result = await authorize(
        visitor_tools, tool_context_for(empty_session), "Joana Ribeiro", "2030-04-22"
    )
    assert result["status"] == "aguardando_confirmacao"


async def test_authorize_does_not_see_other_apartments(
    visitor_tools, tool_context_for, empty_session
):
    result = await authorize(
        visitor_tools, tool_context_for(empty_session), "Marina Duarte", "2030-03-16"
    )
    assert result["status"] == "aguardando_confirmacao"


async def test_authorize_two_pending_requests_one_row(
    visitor_tools, tool_context_for, empty_session, engine
):
    for _ in range(2):
        await authorize(visitor_tools, tool_context_for(empty_session), **JOANA)
    first = await approve(visitor_tools, tool_context_for, empty_session)
    second = await approve(visitor_tools, tool_context_for, empty_session)
    assert (first["status"], second["status"]) == ("autorizado", "ja_autorizado")
    assert len(await rows(engine, "apartment = '101'")) == 1


@pytest.mark.parametrize("nome", ["", "   ", "J", "x" * 101])
async def test_authorize_invalid_name(visitor_tools, tool_context_for, empty_session, engine, nome):
    ctx = tool_context_for(empty_session)
    result = await authorize(visitor_tools, ctx, nome, "2030-04-21")
    assert result == {
        "status": "nome_invalido",
        "mensagem": "Informe o nome do visitante, com 2 a 100 caracteres.",
    }
    assert requested(ctx) == {}
    assert await seed_only(engine)


@pytest.mark.parametrize("nome", ["Jo", "x" * 100])
async def test_authorize_name_limits_are_accepted(
    visitor_tools, tool_context_for, empty_session, nome
):
    result = await authorize(visitor_tools, tool_context_for(empty_session), nome, "2030-04-21")
    assert result["status"] == "aguardando_confirmacao"


@pytest.mark.parametrize("data", ["21/04/2030", "2030-02-30", "2030-4-21", ""])
async def test_authorize_invalid_date(visitor_tools, tool_context_for, empty_session, engine, data):
    ctx = tool_context_for(empty_session)
    result = await authorize(visitor_tools, ctx, "Joana Ribeiro", data)
    assert result == {
        "status": "data_invalida",
        "mensagem": "Informe a data no formato AAAA-MM-DD.",
    }
    assert requested(ctx) == {}
    assert await seed_only(engine)


async def test_authorize_invalid_arguments_with_approval(
    visitor_tools, tool_context_for, empty_session, engine
):
    short = await approve(visitor_tools, tool_context_for, empty_session, nome="J")
    bad_date = await approve(visitor_tools, tool_context_for, empty_session, data="21/04/2030")
    assert short["status"] == "nome_invalido"
    assert bad_date["status"] == "data_invalida"
    assert await seed_only(engine)


async def test_authorize_past_date_is_accepted(visitor_tools, tool_context_for, empty_session):
    result = await authorize(
        visitor_tools, tool_context_for(empty_session), "Joana Ribeiro", "2020-01-01"
    )
    assert result["status"] == "aguardando_confirmacao"


async def test_authorize_ignores_apartment_and_confirmation_arguments(
    visitor_tools, tool_context_for, empty_session, engine
):
    ctx = tool_context_for(empty_session)
    result = await visitor_tools[vt.AUTHORIZE_TOOL](**JOANA, tool_context=ctx)
    assert result["status"] == "aguardando_confirmacao"
    assert await seed_only(engine)
    approved = tool_context_for(empty_session, confirmed=True)
    await visitor_tools[vt.AUTHORIZE_TOOL](**JOANA, tool_context=approved)
    assert await rows(engine, "name = 'Joana Ribeiro'") == [("101", "Joana Ribeiro", "2030-04-21")]
    assert await rows(engine, "apartment = '302'") == [("302", "Marina Duarte", "2030-03-16")]


# --- list ------------------------------------------------------------------------------------


async def test_list_returns_only_session_apartment(
    visitor_tools, tool_context_for, empty_session, session_201
):
    mine = await visitor_tools[vt.LIST_TOOL](tool_context_for(empty_session))
    other = await visitor_tools[vt.LIST_TOOL](tool_context_for(session_201))
    assert mine == {"status": "ok", "visitantes": []}
    assert other["visitantes"] == [{"nome": "Paulo Nogueira", "data": "2030-03-23"}]


async def test_list_shows_authorized_visitor(visitor_tools, tool_context_for, empty_session):
    await approve(visitor_tools, tool_context_for, empty_session)
    result = await visitor_tools[vt.LIST_TOOL](tool_context_for(empty_session))
    assert result["visitantes"] == [{"nome": "Joana Ribeiro", "data": "2030-04-21"}]


async def test_list_omits_pending_request(visitor_tools, tool_context_for, empty_session):
    await authorize(visitor_tools, tool_context_for(empty_session), **JOANA)
    result = await visitor_tools[vt.LIST_TOOL](tool_context_for(empty_session))
    assert result["visitantes"] == []


async def test_list_is_ordered_by_date_then_name(visitor_tools, tool_context_for, empty_session):
    for nome, data in [("Zeca", "2030-05-01"), ("Beto", "2030-05-02"), ("Ana", "2030-05-01")]:
        await approve(visitor_tools, tool_context_for, empty_session, nome, data)
    result = await visitor_tools[vt.LIST_TOOL](tool_context_for(empty_session))
    assert [(v["data"], v["nome"]) for v in result["visitantes"]] == [
        ("2030-05-01", "Ana"),
        ("2030-05-01", "Zeca"),
        ("2030-05-02", "Beto"),
    ]


async def test_list_item_has_only_name_and_date(visitor_tools, tool_context_for, session_201):
    result = await visitor_tools[vt.LIST_TOOL](tool_context_for(session_201))
    assert set(result["visitantes"][0]) == {"nome", "data"}


# --- failures --------------------------------------------------------------------------------


async def test_missing_apartment_in_state(visitor_tools, tool_context_for, empty_session, engine):
    ctx = tool_context_for(empty_session, state={})
    listed = await visitor_tools[vt.LIST_TOOL](ctx)
    authorized = await authorize(visitor_tools, ctx, **JOANA)
    approved = await authorize(visitor_tools, tool_context_for(empty_session, True, {}), **JOANA)
    for result in (listed, authorized, approved):
        assert result["status"] == "servico_indisponivel"
    assert requested(ctx) == {}
    assert await seed_only(engine)


async def test_store_failure_returns_typed_result(
    offline_visitor_tools, tool_context_for, empty_session
):
    ctx = tool_context_for(empty_session)
    listed = await offline_visitor_tools[vt.LIST_TOOL](ctx)
    asked = await authorize(offline_visitor_tools, ctx, **JOANA)
    approved = await authorize(
        offline_visitor_tools, tool_context_for(empty_session, confirmed=True), **JOANA
    )
    for result in (listed, asked, approved):
        assert result["status"] == "servico_indisponivel"
        assert result["mensagem"] == FAILURE_MESSAGE
    assert requested(ctx) == {}


async def test_store_failure_result_has_no_internal_data(
    offline_visitor_tools, tool_context_for, empty_session
):
    result = await offline_visitor_tools[vt.LIST_TOOL](tool_context_for(empty_session))
    dump = str(result).lower()
    for secret in ("aurora:aurora", "localhost", "5999", "select", "postgresql"):
        assert secret not in dump


async def test_tools_write_nothing_to_state(visitor_tools, tool_context_for, empty_session):
    for confirmed in (None, True, False):
        ctx = tool_context_for(empty_session, confirmed=confirmed)
        before = ctx.state.to_dict()
        await authorize(visitor_tools, ctx, "Ana Lima", "2030-06-01")
        await visitor_tools[vt.LIST_TOOL](ctx)
        assert ctx.state.to_dict() == before
        assert ctx.actions.state_delta == {}
