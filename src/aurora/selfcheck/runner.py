import asyncio
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TextIO

from aurora.config import DATA_DIR
from aurora.selfcheck.checks import CheckFailed, foreign_bylaws_lines
from aurora.selfcheck.client import AuroraClient
from aurora.selfcheck.flow import STEPS, FlowContext, Step
from aurora.selfcheck.options import QUOTA_WARNING, SelfCheckOptions, parse_args
from aurora.selfcheck.process import ApiProcess


def _emit(out: TextIO, line: str) -> None:
    print(line, file=out, flush=True)


def _log_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    return Path(tempfile.gettempdir()) / f"aurora-selfcheck-api-{stamp}.log"


async def _run_step(step: Step, ctx: FlowContext) -> str | None:
    """Devolve None quando o passo passa, ou o motivo da falha."""
    try:
        await step.run(ctx)
    except CheckFailed as exc:
        return exc.reason
    except Exception as exc:  # noqa: BLE001 - qualquer erro inesperado vira FAIL
        return f"erro inesperado: {type(exc).__name__}: {exc}"
    return None


async def run(
    options: SelfCheckOptions,
    out: TextIO = sys.stdout,
    steps: tuple[Step, ...] = STEPS,
) -> int:
    _emit(out, QUOTA_WARNING)
    api = ApiProcess(options.api_cmd, options.base_url, _log_path())
    failed: dict[int, str] = {}
    passed = 0
    try:
        async with AuroraClient(options.base_url) as client:
            ctx = FlowContext.build(
                client, api, options, foreign_bylaws_lines(DATA_DIR / "regulamento.md")
            )
            for step in steps:
                blocking = [n for n in sorted(step.depends_on) if n in failed]
                if blocking:
                    reason: str | None = f"depende do passo {blocking[0]}"
                else:
                    reason = await _run_step(step, ctx)
                if reason is None:
                    passed += 1
                    _emit(out, f"Passo {step.number}: PASS")
                else:
                    failed[step.number] = reason
                    _emit(out, f"Passo {step.number}: FAIL — {reason}")
    finally:
        await api.stop()
        _emit(out, f"{passed}/{len(steps)} passos passaram")
        if failed and api.started:
            _emit(out, f"Log da API: {api.log_path}")
    return 0 if not failed else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(parse_args(argv)))
