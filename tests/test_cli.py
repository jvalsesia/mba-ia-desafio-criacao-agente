import pytest

from aurora import cli
from aurora.db import DatabaseUnavailableError
from aurora.store.errors import SeedDataError, StoreError


@pytest.fixture(autouse=True)
def bootstrap_calls(monkeypatch):
    calls = []

    async def fake(url, *a, **k):
        calls.append(url)

    monkeypatch.setattr(cli, "bootstrap_database", fake)
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
