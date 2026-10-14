import json
import socket
import subprocess
import tomllib
from pathlib import Path

from aurora.selfcheck.options import QUOTA_WARNING

ROOT = Path(__file__).resolve().parent.parent


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run_command(tmp_path, *, fault=None, port=None, listen=False):
    port = port or free_port()
    state = tmp_path / "estado.json"
    api = f"uv run python -m tests.selfcheck_fake servir --porta {port} --estado {state}"
    restore = f"uv run python -m tests.selfcheck_fake restaurar --estado {state}"
    if fault:
        api += f" --falha {fault}"
    result = subprocess.run(
        [
            "uv",
            "run",
            "aurora-selfcheck",
            "--api-cmd",
            api,
            "--restore-cmd",
            restore,
            "--base-url",
            f"http://127.0.0.1:{port}",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    return result, state


def test_correct_fake_reports_14_of_14(tmp_path):
    result, state = run_command(tmp_path)
    lines = result.stdout.splitlines()
    assert result.returncode == 0, result.stdout + result.stderr
    assert lines[0] == QUOTA_WARNING
    assert [line for line in lines if line.startswith("Passo ")] == [
        f"Passo {n}: PASS" for n in range(1, 15)
    ]
    assert lines[-1] == "14/14 passos passaram"
    stats = json.loads(state.read_text(encoding="utf-8"))["estatisticas"]
    assert stats["inicios"] == 2
    assert stats["encerramentos"] == 2


def test_fault_reports_fail_and_exit_1(tmp_path):
    result, _ = run_command(tmp_path, fault="disputa-dupla")
    lines = result.stdout.splitlines()
    assert result.returncode == 1
    assert any(line.startswith("Passo 14: FAIL — ") for line in lines)
    assert "13/14 passos passaram" in lines
    assert lines[-1].startswith("Log da API: ")


def test_port_busy_reports_step_1(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        port = sock.getsockname()[1]
        result, state = run_command(tmp_path, port=port)
    lines = result.stdout.splitlines()
    assert result.returncode == 1
    assert any(line.startswith("Passo 1: FAIL — ") and str(port) in line for line in lines)
    assert lines[-1] == "0/14 passos passaram"
    assert not state.exists()


def test_script_registered():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["scripts"]["aurora-selfcheck"] == "aurora.cli:run_selfcheck"
