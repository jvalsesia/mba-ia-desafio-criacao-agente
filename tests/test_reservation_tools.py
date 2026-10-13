import re

import pytest
from sqlalchemy import text

import aurora.agents.reservation_tools as rt

SEED_CODES = {"RSV-1377", "RSV-4821", "RSV-2950"}
FAILURE_MESSAGE = "Não consegui concluir o pedido agora. Tente novamente em instantes."


async def rows(engine, where="true"):
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT code, apartment, area_id, day::text AS day, status "
                f"FROM reservations WHERE {where} ORDER BY code"
            )
        )
        return [tuple(r) for r in result]


async def active(engine, **by):
    clauses = ["status = 'active'", *(f"{k} = '{v}'" for k, v in by.items())]
    return await rows(engine, " AND ".join(clauses))


async def codes(engine):
    return {r[0] for r in await rows(engine)}


def requested(ctx):
    return ctx.actions.requested_tool_confirmations


# --- reserve ---------------------------------------------------------------------------------


async def test_reserve_free_area_creates_reservation(
    reservation_tools, tool_context_for, empty_session, engine
):
    ctx = tool_context_for(empty_session)
    result = await reservation_tools[rt.RESERVE_TOOL]("quadra", "2030-04-06", ctx)
    assert result["status"] == "reservada"
    assert re.fullmatch(r"RSV-\d+", result["codigo"])
    assert result["codigo"] not in SEED_CODES
    assert requested(ctx) == {}
    assert await active(engine, apartment="101", area_id="quadra", day="2030-04-06")


async def test_reserve_free_area_taken_date(
    reservation_tools, tool_context_for, session_201, engine
):
    ctx = tool_context_for(session_201)
    result = await reservation_tools[rt.RESERVE_TOOL]("quadra", "2030-03-09", ctx)
    assert result == {"status": "data_indisponivel", "mensagem": "Essa data não está disponível."}
    assert await codes(engine) == SEED_CODES


async def test_reserve_fee_area_requests_confirmation(
    reservation_tools, tool_context_for, empty_session, engine
):
    ctx = tool_context_for(empty_session)
    result = await reservation_tools[rt.RESERVE_TOOL]("salao-de-festas", "2030-04-20", ctx)
    assert result["status"] == "aguardando_confirmacao"
    request = requested(ctx)["fc-tool"]
    assert request.hint == "Reserva com taxa"
    assert request.payload == {"area": "salao-de-festas", "data": "2030-04-20", "taxa": 150.0}
    assert await codes(engine) == SEED_CODES


async def test_reserve_fee_area_marks_result_as_final(
    reservation_tools, tool_context_for, empty_session
):
    ctx = tool_context_for(empty_session)
    await reservation_tools[rt.RESERVE_TOOL]("salao-de-festas", "2030-04-20", ctx)
    assert ctx.actions.skip_summarization is True


async def test_reserve_barbecue_requests_confirmation(
    reservation_tools, tool_context_for, empty_session, engine
):
    ctx = tool_context_for(empty_session)
    result = await reservation_tools[rt.RESERVE_TOOL]("churrasqueira", "2030-04-27", ctx)
    assert result["status"] == "aguardando_confirmacao"
    assert requested(ctx)["fc-tool"].payload["taxa"] == 80.0
    assert await codes(engine) == SEED_CODES


async def test_reserve_fee_area_taken_date_skips_confirmation(
    reservation_tools, tool_context_for, empty_session
):
    ctx = tool_context_for(empty_session)
    result = await reservation_tools[rt.RESERVE_TOOL]("salao-de-festas", "2030-03-16", ctx)
    assert result["status"] == "data_indisponivel"
    assert set(result) == {"status", "mensagem"}
    assert requested(ctx) == {}
    assert "RSV-4821" not in str(result) and "302" not in str(result)


async def test_reserve_approved_creates_reservation(
    reservation_tools, tool_context_for, empty_session, engine
):
    ctx = tool_context_for(empty_session, confirmed=True)
    result = await reservation_tools[rt.RESERVE_TOOL]("salao-de-festas", "2030-04-20", ctx)
    assert result["status"] == "reservada"
    assert requested(ctx) == {}
    found = await active(engine, area_id="salao-de-festas", day="2030-04-20")
    assert [r[1] for r in found] == ["101"]


async def test_reserve_denied_writes_nothing(
    reservation_tools, tool_context_for, empty_session, engine
):
    ctx = tool_context_for(empty_session, confirmed=False)
    result = await reservation_tools[rt.RESERVE_TOOL]("salao-de-festas", "2030-04-20", ctx)
    assert result == {
        "status": "nao_confirmada",
        "mensagem": "A reserva não foi confirmada. Nada foi alterado.",
    }
    assert requested(ctx) == {}
    assert await codes(engine) == SEED_CODES


async def test_reserve_approved_after_date_was_taken(
    reservation_tools, tool_context_for, empty_session, session_201, engine
):
    other = tool_context_for(session_201, confirmed=True)
    taken = await reservation_tools[rt.RESERVE_TOOL]("salao-de-festas", "2030-04-20", other)
    assert taken["status"] == "reservada"
    ctx = tool_context_for(empty_session, confirmed=True)
    result = await reservation_tools[rt.RESERVE_TOOL]("salao-de-festas", "2030-04-20", ctx)
    assert result == {
        "status": "data_indisponivel",
        "mensagem": "Essa data não está mais disponível.",
    }
    found = await active(engine, area_id="salao-de-festas", day="2030-04-20")
    assert [r[1] for r in found] == ["201"]


async def test_reserve_fee_comes_from_catalog(
    reservation_tools, tool_context_for, empty_session, engine
):
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE areas SET fee = 200 WHERE id = 'salao-de-festas'"))
    ctx = tool_context_for(empty_session)
    await reservation_tools[rt.RESERVE_TOOL]("salao-de-festas", "2030-04-20", ctx)
    assert requested(ctx)["fc-tool"].payload["taxa"] == 200.0


async def test_reserve_free_area_ignores_confirmation(
    reservation_tools, tool_context_for, empty_session
):
    ctx = tool_context_for(empty_session, confirmed=False)
    result = await reservation_tools[rt.RESERVE_TOOL]("quadra", "2030-04-06", ctx)
    assert result["status"] == "reservada"


@pytest.mark.parametrize("value", ["06/04/2030", "2030-02-30", "2030-4-6", "20300406", ""])
async def test_reserve_invalid_date(
    reservation_tools, tool_context_for, empty_session, engine, value
):
    ctx = tool_context_for(empty_session)
    result = await reservation_tools[rt.RESERVE_TOOL]("salao-de-festas", value, ctx)
    assert result == {
        "status": "data_invalida",
        "mensagem": "Informe a data no formato AAAA-MM-DD.",
    }
    assert requested(ctx) == {}
    assert await codes(engine) == SEED_CODES


async def test_reserve_unknown_area(reservation_tools, tool_context_for, empty_session):
    ctx = tool_context_for(empty_session)
    result = await reservation_tools[rt.RESERVE_TOOL]("piscina", "2030-04-06", ctx)
    assert result["status"] == "area_desconhecida"
    assert set(result["areas"]) == {"salao-de-festas", "churrasqueira", "quadra"}
    assert requested(ctx) == {}


async def test_reserve_past_date_is_accepted(reservation_tools, tool_context_for, empty_session):
    ctx = tool_context_for(empty_session)
    result = await reservation_tools[rt.RESERVE_TOOL]("quadra", "2020-01-01", ctx)
    assert result["status"] == "reservada"


async def test_reserve_normalizes_area(reservation_tools, tool_context_for, empty_session):
    ctx = tool_context_for(empty_session)
    result = await reservation_tools[rt.RESERVE_TOOL](" Quadra ", "2030-04-06", ctx)
    assert result["status"] == "reservada" and result["area"] == "quadra"


async def test_reserve_ignores_apartment_argument(
    reservation_tools, tool_context_for, empty_session, engine
):
    from google.adk.tools import FunctionTool

    tool = FunctionTool(reservation_tools[rt.RESERVE_TOOL])
    ctx = tool_context_for(empty_session)
    result = await tool.run_async(
        args={"area": "quadra", "data": "2030-04-06", "apartamento": "302"}, tool_context=ctx
    )
    assert result["status"] == "reservada"
    assert await active(engine, area_id="quadra", day="2030-04-06", apartment="101")
    assert [r[0] for r in await active(engine, apartment="302")] == ["RSV-4821"]


# --- cancel ----------------------------------------------------------------------------------


async def test_cancel_by_area_and_date(reservation_tools, tool_context_for, empty_session, engine):
    ctx = tool_context_for(empty_session)
    result = await reservation_tools[rt.CANCEL_TOOL](ctx, area="quadra", data="2030-03-09")
    assert result == {
        "status": "cancelada",
        "codigo": "RSV-1377",
        "area": "quadra",
        "data": "2030-03-09",
    }
    assert await active(engine, apartment="101") == []
    assert [r[4] for r in await rows(engine, "code = 'RSV-1377'")] == ["cancelled"]


async def test_cancel_by_code(reservation_tools, tool_context_for, empty_session):
    ctx = tool_context_for(empty_session)
    result = await reservation_tools[rt.CANCEL_TOOL](ctx, codigo="RSV-1377")
    assert result["status"] == "cancelada"


async def test_cancel_code_is_normalized(reservation_tools, tool_context_for, empty_session):
    ctx = tool_context_for(empty_session)
    result = await reservation_tools[rt.CANCEL_TOOL](ctx, codigo=" rsv-1377 ")
    assert result["status"] == "cancelada"


async def test_cancel_other_apartment_by_area_and_date(
    reservation_tools, tool_context_for, empty_session, engine
):
    ctx = tool_context_for(empty_session)
    result = await reservation_tools[rt.CANCEL_TOOL](ctx, area="salao-de-festas", data="2030-03-16")
    assert result == {
        "status": "nao_encontrada",
        "mensagem": "Não encontrei uma reserva sua nessa data.",
    }
    assert "RSV-4821" not in str(result)
    assert [r[0] for r in await active(engine, apartment="302")] == ["RSV-4821"]


async def test_cancel_other_apartment_code(
    reservation_tools, tool_context_for, empty_session, engine
):
    ctx = tool_context_for(empty_session)
    result = await reservation_tools[rt.CANCEL_TOOL](ctx, codigo="RSV-4821")
    assert result == {
        "status": "nao_encontrada",
        "mensagem": "Não encontrei uma reserva sua com esse código.",
    }
    assert [r[0] for r in await active(engine, apartment="302")] == ["RSV-4821"]


async def test_cancel_not_found_results_are_identical(
    reservation_tools, tool_context_for, empty_session
):
    cancel = reservation_tools[rt.CANCEL_TOOL]
    ctx = tool_context_for(empty_session)
    await cancel(ctx, codigo="RSV-1377")
    results = [
        await cancel(ctx, codigo="RSV-4821"),
        await cancel(ctx, codigo="RSV-0000"),
        await cancel(ctx, codigo="RSV-1377"),
    ]
    assert results[0] == results[1] == results[2]


@pytest.mark.parametrize(
    "args", [{}, {"area": "quadra"}, {"data": "2030-03-09"}], ids=["none", "area", "date"]
)
async def test_cancel_without_identification(
    reservation_tools, tool_context_for, empty_session, engine, args
):
    ctx = tool_context_for(empty_session)
    result = await reservation_tools[rt.CANCEL_TOOL](ctx, **args)
    assert result["status"] == "parametros_invalidos" and result["mensagem"]
    assert await codes(engine) == SEED_CODES
    assert len(await active(engine)) == 3


async def test_cancel_code_takes_precedence(
    reservation_tools, tool_context_for, session_201, engine
):
    ctx = tool_context_for(session_201)
    result = await reservation_tools[rt.CANCEL_TOOL](
        ctx, area="quadra", data="2030-03-09", codigo="RSV-2950"
    )
    assert result["status"] == "cancelada" and result["codigo"] == "RSV-2950"
    assert [r[0] for r in await active(engine, apartment="101")] == ["RSV-1377"]


async def test_cancel_invalid_date(reservation_tools, tool_context_for, empty_session):
    ctx = tool_context_for(empty_session)
    result = await reservation_tools[rt.CANCEL_TOOL](ctx, area="quadra", data="09/03/2030")
    assert result["status"] == "data_invalida"


async def test_cancel_never_requests_confirmation(
    reservation_tools, tool_context_for, empty_session
):
    reserve = reservation_tools[rt.RESERVE_TOOL]
    approved = tool_context_for(empty_session, confirmed=True)
    await reserve("salao-de-festas", "2030-04-20", approved)
    ctx = tool_context_for(empty_session)
    result = await reservation_tools[rt.CANCEL_TOOL](ctx, area="salao-de-festas", data="2030-04-20")
    assert result["status"] == "cancelada"
    assert requested(ctx) == {}


# --- list ------------------------------------------------------------------------------------


async def test_list_returns_only_session_apartment(
    reservation_tools, tool_context_for, empty_session, session_201
):
    list_ = reservation_tools[rt.LIST_TOOL]
    own = await list_(tool_context_for(empty_session))
    other = await list_(tool_context_for(session_201))
    assert own == {
        "status": "ok",
        "reservas": [{"codigo": "RSV-1377", "area": "quadra", "data": "2030-03-09"}],
    }
    assert other["reservas"] == [
        {"codigo": "RSV-2950", "area": "churrasqueira", "data": "2030-03-23"}
    ]
    assert "RSV-4821" not in str(own) and "Marina Duarte" not in str(own)


async def test_list_omits_cancelled(reservation_tools, tool_context_for, empty_session):
    ctx = tool_context_for(empty_session)
    await reservation_tools[rt.CANCEL_TOOL](ctx, codigo="RSV-1377")
    result = await reservation_tools[rt.LIST_TOOL](ctx)
    assert result == {"status": "ok", "reservas": []}


async def test_list_is_ordered_by_date_then_code(
    reservation_tools, tool_context_for, empty_session
):
    ctx = tool_context_for(empty_session)
    await reservation_tools[rt.RESERVE_TOOL]("quadra", "2030-05-01", ctx)
    await reservation_tools[rt.RESERVE_TOOL](
        "churrasqueira", "2030-02-01", tool_context_for(empty_session, True)
    )
    result = await reservation_tools[rt.LIST_TOOL](ctx)
    assert [r["data"] for r in result["reservas"]] == ["2030-02-01", "2030-03-09", "2030-05-01"]


# --- availability and areas -----------------------------------------------------------------


async def test_availability_free_and_taken(reservation_tools, tool_context_for, empty_session):
    ctx = tool_context_for(empty_session)
    check = reservation_tools[rt.AVAILABILITY_TOOL]
    assert await check("salao-de-festas", "2030-04-20", ctx) == {
        "status": "ok",
        "area": "salao-de-festas",
        "data": "2030-04-20",
        "disponibilidade": "livre",
    }
    assert (await check("salao-de-festas", "2030-03-16", ctx))["disponibilidade"] == "ocupada"


async def test_availability_result_has_no_owner_data(
    reservation_tools, tool_context_for, empty_session
):
    ctx = tool_context_for(empty_session)
    result = await reservation_tools[rt.AVAILABILITY_TOOL]("salao-de-festas", "2030-03-16", ctx)
    assert set(result) == {"status", "area", "data", "disponibilidade"}
    assert "RSV-4821" not in str(result) and "302" not in str(result)


async def test_availability_unknown_area(reservation_tools, tool_context_for, empty_session):
    ctx = tool_context_for(empty_session)
    result = await reservation_tools[rt.AVAILABILITY_TOOL]("piscina", "2030-03-16", ctx)
    assert result["status"] == "area_desconhecida"


async def test_availability_invalid_date(reservation_tools, tool_context_for, empty_session):
    ctx = tool_context_for(empty_session)
    result = await reservation_tools[rt.AVAILABILITY_TOOL]("quadra", "16/03/2030", ctx)
    assert result["status"] == "data_invalida"


async def test_areas_lists_catalog_with_fees(reservation_tools, tool_context_for, empty_session):
    result = await reservation_tools[rt.AREAS_TOOL](tool_context_for(empty_session))
    assert result["status"] == "ok" and len(result["areas"]) == 3
    assert {"id": "salao-de-festas", "nome": "Salão de festas", "taxa": 150.0} in result["areas"]
    assert {"id": "churrasqueira", "nome": "Churrasqueira", "taxa": 80.0} in result["areas"]
    assert {"id": "quadra", "nome": "Quadra poliesportiva", "taxa": 0.0} in result["areas"]
    assert all(isinstance(a["taxa"], float) for a in result["areas"])


# --- apartment, failures, state --------------------------------------------------------------

CALLS = {
    rt.RESERVE_TOOL: lambda ctx: ((), {"area": "quadra", "data": "2030-04-06"}),
    rt.CANCEL_TOOL: lambda ctx: ((), {"codigo": "RSV-1377"}),
    rt.LIST_TOOL: lambda ctx: ((), {}),
    rt.AVAILABILITY_TOOL: lambda ctx: ((), {"area": "quadra", "data": "2030-04-06"}),
    rt.AREAS_TOOL: lambda ctx: ((), {}),
}


async def call(tools, name, ctx):
    _, kwargs = CALLS[name](ctx)
    func = tools[name]
    if name in (rt.RESERVE_TOOL, rt.AVAILABILITY_TOOL):
        return await func(kwargs["area"], kwargs["data"], ctx)
    return await func(ctx, **kwargs) if name == rt.CANCEL_TOOL else await func(ctx)


async def test_missing_apartment_in_state(
    reservation_tools, tool_context_for, empty_session, engine
):
    ctx = tool_context_for(empty_session, state={})
    for name in CALLS:
        result = await call(reservation_tools, name, ctx)
        assert result["status"] == "servico_indisponivel"
    assert await codes(engine) == SEED_CODES
    assert len(await active(engine)) == 3


@pytest.mark.parametrize("name", list(CALLS))
async def test_store_failure_returns_typed_result(
    offline_reservation_tools, tool_context_for, empty_session, name
):
    ctx = tool_context_for(empty_session)
    result = await call(offline_reservation_tools, name, ctx)
    assert result == {"status": "servico_indisponivel", "mensagem": FAILURE_MESSAGE}
    assert requested(ctx) == {}


async def test_store_failure_result_has_no_internal_data(
    offline_reservation_tools, tool_context_for, empty_session
):
    ctx = tool_context_for(empty_session)
    result = await offline_reservation_tools[rt.LIST_TOOL](ctx)
    flat = str(result)
    for forbidden in ("aurora:aurora", "localhost", "5999", "SELECT", "postgresql"):
        assert forbidden not in flat


@pytest.mark.parametrize("name", list(CALLS))
async def test_tools_write_nothing_to_state(
    reservation_tools, tool_context_for, empty_session, name
):
    ctx = tool_context_for(empty_session)
    before = dict(empty_session.state)
    await call(reservation_tools, name, ctx)
    assert dict(empty_session.state) == before
    assert ctx.actions.state_delta == {}
