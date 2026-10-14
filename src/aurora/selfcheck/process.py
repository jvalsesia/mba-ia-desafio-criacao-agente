import asyncio
import os
import signal
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from aurora.selfcheck.checks import CheckFailed
from aurora.selfcheck.options import KILL_TIMEOUT, STARTUP_TIMEOUT, STOP_TIMEOUT

PORT_FREE_TIMEOUT = 10.0
POLL_INTERVAL = 0.5


def _host_port(base_url: str) -> tuple[str, int]:
    parsed = urlparse(base_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def ensure_port_free(base_url: str) -> None:
    host, port = _host_port(base_url)
    if _port_open(host, port):
        raise CheckFailed(f"a porta {port} já está em uso; pare a API antes de rodar o self-check")


async def run_restore(cmd: list[str]) -> None:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise CheckFailed(f"restauração não executou: {exc}") from exc
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        lines = stderr.decode(errors="replace").strip().splitlines()
        last = lines[-1] if lines else ""
        suffix = f": {last}" if last else ""
        raise CheckFailed(f"a restauração terminou com código {proc.returncode}{suffix}")


class ApiProcess:
    def __init__(self, cmd: list[str], base_url: str, log_path: Path) -> None:
        self.cmd = cmd
        self.base_url = base_url
        self.log_path = log_path
        self._proc: subprocess.Popen | None = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    async def _healthy(self, client: httpx.AsyncClient) -> bool:
        try:
            reply = await client.get(f"{self.base_url}/health")
        except httpx.HTTPError:
            return False
        return reply.status_code == 200

    async def start(self) -> None:
        with self.log_path.open("ab") as log:
            try:
                self._proc = subprocess.Popen(
                    self.cmd,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except OSError as exc:
                raise CheckFailed(f"não foi possível iniciar a API: {exc}") from exc
        deadline = time.monotonic() + STARTUP_TIMEOUT
        async with httpx.AsyncClient(timeout=2.0) as client:
            while True:
                code = self._proc.poll()
                if code is not None:
                    raise CheckFailed(
                        f"a API encerrou com código {code} antes de responder em /health"
                    )
                if await self._healthy(client):
                    return
                if time.monotonic() >= deadline:
                    await self.stop()
                    raise CheckFailed(f"a API não respondeu em /health em {STARTUP_TIMEOUT:.0f} s")
                await asyncio.sleep(POLL_INTERVAL)

    def _signal_group(self, sig: int) -> None:
        assert self._proc is not None
        try:
            os.killpg(self._proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass

    async def _wait_exit(self, timeout: float) -> bool:
        assert self._proc is not None
        deadline = time.monotonic() + timeout
        while self._proc.poll() is None:
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(0.1)
        return True

    async def stop(self) -> None:
        proc = self._proc
        if proc is None:
            return
        if proc.poll() is not None:
            return
        self._signal_group(signal.SIGINT)
        if not await self._wait_exit(STOP_TIMEOUT):
            self._signal_group(signal.SIGTERM)
            if not await self._wait_exit(KILL_TIMEOUT):
                self._signal_group(signal.SIGKILL)
                await self._wait_exit(KILL_TIMEOUT)
        host, port = _host_port(self.base_url)
        deadline = time.monotonic() + PORT_FREE_TIMEOUT
        while _port_open(host, port) and time.monotonic() < deadline:
            await asyncio.sleep(0.2)
