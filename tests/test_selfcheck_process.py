import json
import socket
import sys

import pytest

from aurora.selfcheck import process
from aurora.selfcheck.checks import CheckFailed
from aurora.selfcheck.process import ApiProcess, ensure_port_free, run_restore
from tests.selfcheck_fake import restore_state


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def fake_cmd(port: int, state) -> list[str]:
    return [
        sys.executable,
        "-m",
        "tests.selfcheck_fake",
        "servir",
        "--porta",
        str(port),
        "--estado",
        str(state),
    ]


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def test_port_in_use_fails():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        port = sock.getsockname()[1]
        with pytest.raises(CheckFailed) as caught:
            ensure_port_free(f"http://127.0.0.1:{port}")
    assert str(port) in caught.value.reason


async def test_restore_failure_reports_exit_code():
    cmd = [sys.executable, "-c", "import sys; print('boom', file=sys.stderr); sys.exit(1)"]
    with pytest.raises(CheckFailed) as caught:
        await run_restore(cmd)
    assert "1" in caught.value.reason
    assert "boom" in caught.value.reason


async def test_start_waits_for_health(tmp_path):
    state = tmp_path / "estado.json"
    restore_state(state)
    port = free_port()
    api = ApiProcess(fake_cmd(port, state), f"http://127.0.0.1:{port}", tmp_path / "api.log")
    try:
        await api.start()
        assert api.running
    finally:
        await api.stop()
    assert not api.running


async def test_start_detects_early_exit(tmp_path):
    port = free_port()
    api = ApiProcess(
        [sys.executable, "-c", "raise SystemExit(3)"],
        f"http://127.0.0.1:{port}",
        tmp_path / "api.log",
    )
    with pytest.raises(CheckFailed) as caught:
        await api.start()
    assert "3" in caught.value.reason


async def test_stop_is_graceful_and_frees_port(tmp_path):
    state = tmp_path / "estado.json"
    restore_state(state)
    port = free_port()
    api = ApiProcess(fake_cmd(port, state), f"http://127.0.0.1:{port}", tmp_path / "api.log")
    await api.start()
    await api.stop()
    stats = json.loads(state.read_text(encoding="utf-8"))["estatisticas"]
    assert stats["encerramentos"] == 1
    assert not port_open(port)


async def test_stop_escalates_when_sigint_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(process, "STOP_TIMEOUT", 0.5)
    port = free_port()
    code = (
        "import signal, http.server\n"
        "signal.signal(signal.SIGINT, signal.SIG_IGN)\n"
        "class H(http.server.BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        self.send_response(200); self.end_headers(); self.wfile.write(b'ok')\n"
        "    def log_message(self, *a): pass\n"
        f"http.server.HTTPServer(('127.0.0.1', {port}), H).serve_forever()\n"
    )
    api = ApiProcess([sys.executable, "-c", code], f"http://127.0.0.1:{port}", tmp_path / "a.log")
    await api.start()
    await api.stop()
    assert not api.running
    assert not port_open(port)
