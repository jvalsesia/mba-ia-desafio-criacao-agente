import os
import tomllib

import pytest

from aurora import cli
from aurora.config import PROJECT_ROOT
from aurora.db import DatabaseUnavailableError
from aurora.restore import RestoreSummary
from aurora.sessions.service import SessionStoreError
from aurora.store.errors import SeedDataError, StoreError


@pytest.fixture(autouse=True)
def bootstrap_calls(monkeypatch):
    calls = []

    async def fake(url, *a, **k):
        calls.append(url)

    monkeypatch.setattr(cli, "bootstrap_database", fake)
    return calls


@pytest.fixture(autouse=True)
def session_bootstrap_calls(monkeypatch):
    calls = []

    async def fake(url, *a, **k):
        calls.append(url)

    monkeypatch.setattr(cli, "bootstrap_sessions", fake)
    return calls


@pytest.fixture
def uvicorn_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **k: calls.append((a, k)))
    return calls


def test_run_api_exits_1_without_key(clean_env, monkeypatch, capsys, uvicorn_calls):
    monkeypatch.setattr(cli, "load_settings", lambda: cli_load_without_env())
    with pytest.raises(SystemExit) as info:
        cli.run_api()
    assert info.value.code == 1
    assert "GOOGLE_API_KEY" in capsys.readouterr().err
    assert uvicorn_calls == []


def cli_load_without_env():
    from aurora.config import load_settings

    return load_settings(env_file=None)


def test_run_api_exits_1_when_database_unreachable(monkeypatch, capsys, uvicorn_calls):
    async def fail(url, *a, **k):
        raise DatabaseUnavailableError("Banco de dados inacessível em localhost:5999")

    monkeypatch.setattr(cli, "wait_for_database", fail)
    with pytest.raises(SystemExit) as info:
        cli.run_api()
    assert info.value.code == 1
    err = capsys.readouterr().err
    assert "localhost:5999" in err and "segredo" not in err
    assert uvicorn_calls == []


def test_run_api_starts_uvicorn_on_fixed_address(monkeypatch, uvicorn_calls):
    async def ok(url, *a, **k):
        return None

    monkeypatch.setattr(cli, "wait_for_database", ok)
    cli.run_api()
    assert uvicorn_calls[0][1] == {"host": "127.0.0.1", "port": 8000}


def test_run_api_prepares_database_before_uvicorn(monkeypatch, bootstrap_calls):
    order = []

    async def ok(url, *a, **k):
        return None

    async def prepare(url, *a, **k):
        order.append("bootstrap")

    monkeypatch.setattr(cli, "wait_for_database", ok)
    monkeypatch.setattr(cli, "bootstrap_database", prepare)
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **k: order.append("uvicorn"))
    cli.run_api()
    assert order == ["bootstrap", "uvicorn"]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (SeedDataError("reservas.json", "JSON inválido"), "reservas.json"),
        (StoreError(), "Serviço de dados indisponível"),
    ],
)
def test_run_api_exits_1_when_preparation_fails(
    monkeypatch, capsys, uvicorn_calls, error, expected
):
    async def ok(url, *a, **k):
        return None

    async def fail(url, *a, **k):
        raise error

    monkeypatch.setattr(cli, "wait_for_database", ok)
    monkeypatch.setattr(cli, "bootstrap_database", fail)
    with pytest.raises(SystemExit) as info:
        cli.run_api()
    assert info.value.code == 1
    assert expected in capsys.readouterr().err
    assert uvicorn_calls == []


def test_run_api_prepares_sessions_before_uvicorn(monkeypatch, uvicorn_calls):
    order = []

    async def ok(url, *a, **k):
        return None

    async def boot_db(url, *a, **k):
        order.append("db")

    async def boot_sessions(url, *a, **k):
        order.append("sessions")

    monkeypatch.setattr(cli, "wait_for_database", ok)
    monkeypatch.setattr(cli, "bootstrap_database", boot_db)
    monkeypatch.setattr(cli, "bootstrap_sessions", boot_sessions)
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **k: order.append("uvicorn"))
    cli.run_api()
    assert order == ["db", "sessions", "uvicorn"]


def test_run_api_exits_1_when_session_storage_fails(monkeypatch, capsys, uvicorn_calls):
    async def ok(url, *a, **k):
        return None

    async def fail(url, *a, **k):
        raise SessionStoreError()

    monkeypatch.setattr(cli, "wait_for_database", ok)
    monkeypatch.setattr(cli, "bootstrap_sessions", fail)
    with pytest.raises(SystemExit) as info:
        cli.run_api()
    assert info.value.code == 1
    assert capsys.readouterr().err.strip()
    assert uvicorn_calls == []


# --- run_restore ---

PASSWORD_URL = "postgresql+asyncpg://aurora:segredo@dbhost:5433/meudb"


@pytest.fixture
def restore_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", PASSWORD_URL)
    monkeypatch.setattr(cli, "load_database_url", lambda: PASSWORD_URL)
    calls = []

    async def wait(url, *a, **k):
        calls.append("espera")

    async def restore(url, *a, **k):
        calls.append("restauração")
        return RestoreSummary(3, 2, 5)

    monkeypatch.setattr(cli, "wait_for_database", wait)
    monkeypatch.setattr(cli, "restore_data", restore)
    return calls


def test_run_restore_prints_summary(restore_env, capsys):
    cli.run_restore()
    out, err = capsys.readouterr()
    lines = out.splitlines()
    assert lines[1:] == [
        "Reservas carregadas: 3",
        "Visitantes carregados: 2",
        "Sessões removidas: 5",
    ]
    assert err == ""


def test_run_restore_prints_target_without_credentials(restore_env, capsys):
    cli.run_restore()
    out = capsys.readouterr().out
    assert "dbhost:5433 (database meudb)" in out
    assert "segredo" not in out


def test_run_restore_waits_for_database_before_restoring(restore_env):
    cli.run_restore()
    assert restore_env == ["espera", "restauração"]


def test_run_restore_does_not_require_gemini_key(restore_env, monkeypatch, capsys):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    cli.run_restore()
    assert "Reservas carregadas: 3" in capsys.readouterr().out
    assert "GOOGLE_API_KEY" not in os.environ


def test_run_restore_exits_1_when_database_unreachable(restore_env, monkeypatch, capsys):
    async def wait(url, *a, **k):
        raise DatabaseUnavailableError("Banco de dados inacessível em dbhost:5433")

    monkeypatch.setattr(cli, "wait_for_database", wait)
    with pytest.raises(SystemExit) as info:
        cli.run_restore()
    out, err = capsys.readouterr()
    assert info.value.code == 1
    assert "dbhost:5433" in err
    assert out == ""
    assert "restauração" not in restore_env


@pytest.mark.parametrize(
    "error", [SeedDataError("reservas.json", "JSON inválido"), StoreError(), SessionStoreError()]
)
def test_run_restore_exits_1_when_restore_fails(restore_env, monkeypatch, capsys, error):
    async def restore(url, *a, **k):
        raise error

    monkeypatch.setattr(cli, "restore_data", restore)
    with pytest.raises(SystemExit) as info:
        cli.run_restore()
    out, err = capsys.readouterr()
    assert info.value.code == 1
    assert str(error) in err
    assert out == ""


def test_run_restore_exits_1_on_invalid_database_url(monkeypatch, capsys):
    real = cli.load_database_url
    monkeypatch.setenv("DATABASE_URL", "nao-e-url://usuario:segredo-teste@")
    monkeypatch.setattr(cli, "load_database_url", lambda: real(env_file=None))
    with pytest.raises(SystemExit) as info:
        cli.run_restore()
    out, err = capsys.readouterr()
    assert info.value.code == 1
    assert "DATABASE_URL" in err
    assert "segredo-teste" not in err
    assert out == ""


def test_run_restore_does_not_start_uvicorn(restore_env, monkeypatch):
    called = []
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **k: called.append(1))
    cli.run_restore()
    assert called == []


def test_restore_script_is_declared():
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    assert data["project"]["scripts"]["aurora-restore"] == "aurora.cli:run_restore"
