import argparse
import shlex
from dataclasses import dataclass

DEFAULT_API_CMD = "uv run aurora-api"
DEFAULT_RESTORE_CMD = "uv run aurora-restore"
DEFAULT_BASE_URL = "http://localhost:8000"

QUOTA_WARNING = (
    "AVISO: o self-check faz chamadas reais ao Gemini (algumas dezenas por execução) "
    "e consome cota da chave configurada no .env."
)
FOLLOW_UP_TEXT = "Sim, pode seguir com o pedido."
MAX_FOLLOW_UPS = 2

REQUEST_TIMEOUT = 120.0
STARTUP_TIMEOUT = 60.0
STOP_TIMEOUT = 15.0
KILL_TIMEOUT = 5.0


@dataclass(frozen=True)
class SelfCheckOptions:
    api_cmd: list[str]
    restore_cmd: list[str]
    base_url: str


def parse_args(argv: list[str] | None = None) -> SelfCheckOptions:
    parser = argparse.ArgumentParser(
        prog="aurora-selfcheck",
        description="Reproduz o fluxo do avaliador (passos 1 a 14) contra a API real.",
    )
    parser.add_argument("--api-cmd", default=DEFAULT_API_CMD, help="comando que sobe a API")
    parser.add_argument(
        "--restore-cmd", default=DEFAULT_RESTORE_CMD, help="comando de restauração dos dados"
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="endereço da API")
    args = parser.parse_args(argv)
    return SelfCheckOptions(
        api_cmd=shlex.split(args.api_cmd),
        restore_cmd=shlex.split(args.restore_cmd),
        base_url=args.base_url.rstrip("/"),
    )
