import pytest

from aurora.db import DatabaseUnavailableError, describe_target, wait_for_database
from tests.conftest import TEST_DATABASE_URL


def test_describe_target_hides_credentials():
    out = describe_target("postgresql+asyncpg://meuuser:minhasenha@dbhost:5555/meudb")
    assert "dbhost:5555" in out and "meudb" in out
    assert "meuuser" not in out and "minhasenha" not in out


async def test_wait_for_database_succeeds():
    await wait_for_database(TEST_DATABASE_URL, timeout_seconds=5)


async def test_wait_for_database_times_out_on_closed_port():
    url = "postgresql+asyncpg://aurora:segredo-teste@localhost:5999/aurora"
    with pytest.raises(DatabaseUnavailableError) as info:
        await wait_for_database(url, timeout_seconds=1, interval_seconds=0.2)
    assert "localhost:5999" in str(info.value)
    assert "segredo-teste" not in str(info.value)
