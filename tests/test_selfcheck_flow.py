import io
import json

import httpx
import pytest

from aurora.config import DATA_DIR
from aurora.selfcheck import flow
from aurora.selfcheck.checks import CheckFailed, foreign_bylaws_lines
from aurora.selfcheck.client import AuroraClient
from aurora.selfcheck.flow import STEPS, FlowContext, Step, converse
from aurora.selfcheck.options import FOLLOW_UP_TEXT, SelfCheckOptions
from aurora.selfcheck.runner import run
from tests.selfcheck_fake import create_app, restore_state

OPTIONS = SelfCheckOptions(api_cmd=["true"], restore_cmd=["true"], base_url="http://fake")


def make_context(tmp_path, *faults):
    path = tmp_path / "estado.json"
    restore_state(path)
    app = create_app(path, set(faults))
    fake = app.state.fake
    fake.startup()
    client = AuroraClient("http://fake", transport=httpx.ASGITransport(app=app))
    lines = foreign_bylaws_lines(DATA_DIR / "regulamento.md")
    return FlowContext.build(client, None, OPTIONS, lines), fake


def stats(fake):
    return json.loads(fake.path.read_text(encoding="utf-8"))["estatisticas"]


async def run_steps(ctx, first, last):
    for step in STEPS[first - 1 : last]:
        await step.run(ctx)


async def test_correct_fake_passes_steps_2_to_12(tmp_path):
    ctx, _ = make_context(tmp_path)
    async with ctx.client:
        await run_steps(ctx, 2, 12)
    state = ctx.state
    assert state.s1 and state.s2
    assert state.approved_hall_id and state.denied_hall_id
    assert state.s1_event_count and state.s1_event_count > 0


async def test_follow_up_sent_until_effect(tmp_path):
    ctx, fake = make_context(tmp_path, "pergunta-antes")
    async with ctx.client:
        await run_steps(ctx, 2, 2)
        await STEPS[5].run(ctx)
    assert stats(fake)["seguimentos"] == 1


async def test_follow_up_limit(tmp_path):
    ctx, fake = make_context(tmp_path, "pergunta-sempre")
    async with ctx.client:
        await run_steps(ctx, 2, 2)
        with pytest.raises(CheckFailed):
            await STEPS[5].run(ctx)
    assert stats(fake)["seguimentos"] == 2


async def test_no_follow_up_in_step_3(tmp_path):
    ctx, fake = make_context(tmp_path, "pergunta-antes")
    async with ctx.client:
        await run_steps(ctx, 2, 3)
    assert stats(fake)["seguimentos"] == 0


async def test_converse_without_until_sends_one_message(tmp_path):
    ctx, fake = make_context(tmp_path)
    async with ctx.client:
        await run_steps(ctx, 2, 2)
        exchange = await converse(ctx, ctx.state.s1, FOLLOW_UP_TEXT)
    assert len(exchange.replies) == 1


FAULT_CASES = [
    ("sessao-200", 2, "200"),
    ("vaza-302", 3, "RSV-4821"),
    ("vaza-302-eventos", 4, "eventos"),
    ("cancela-com-confirmacao", 5, "pendente"),
    ("quadra-com-confirmacao", 6, "pendente"),
    ("grava-antes-da-aprovacao", 7, "2030-04-20"),
    ("reenvio-200", 8, "409"),
    ("id-inexistente-200", 9, "409"),
    ("cita-302", 10, "302"),
    ("texto-confirma", 11, "Joana Ribeiro"),
    ("regulamento-vaza", 12, "VIII"),
]


@pytest.mark.parametrize(("fault", "number", "fragment"), FAULT_CASES)
async def test_step_failure_reasons(tmp_path, fault, number, fragment):
    ctx, _ = make_context(tmp_path, fault)
    async with ctx.client:
        for step in STEPS[1 : number - 1]:
            try:
                await step.run(ctx)
            except CheckFailed:
                pass
        with pytest.raises(CheckFailed) as caught:
            await STEPS[number - 1].run(ctx)
    assert fragment in caught.value.reason


async def test_dependency_skips_dependents(tmp_path):
    async def fail(_):
        raise CheckFailed("quebrou")

    async def ok(_):
        return None

    steps = (
        Step(1, "a", (), ok),
        Step(2, "b", (1,), fail),
        Step(3, "c", (2,), ok),
        Step(4, "d", (1,), ok),
        Step(5, "e", (3, 2), ok),
    )
    out = io.StringIO()
    code = await run(OPTIONS, out, steps)
    lines = out.getvalue().splitlines()
    assert code == 1
    assert "Passo 2: FAIL — quebrou" in lines
    assert "Passo 3: FAIL — depende do passo 2" in lines
    assert "Passo 4: PASS" in lines
    assert "Passo 5: FAIL — depende do passo 2" in lines
    assert "2/5 passos passaram" in lines


async def test_unexpected_exception_becomes_fail():
    async def boom(_):
        raise KeyError("x")

    async def ok(_):
        return None

    out = io.StringIO()
    code = await run(OPTIONS, out, (Step(1, "a", (), boom), Step(2, "b", (), ok)))
    lines = out.getvalue().splitlines()
    assert code == 1
    assert "Passo 1: FAIL — erro inesperado: KeyError: 'x'" in lines
    assert "Passo 2: PASS" in lines


async def test_parallel_approvals_overlap(tmp_path):
    ctx, fake = make_context(tmp_path)
    async with ctx.client:
        await flow.step_14(ctx)
    assert stats(fake)["max_aprovacoes_simultaneas"] == 2
