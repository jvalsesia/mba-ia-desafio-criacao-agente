import hashlib
from pathlib import Path

import pytest
from sqlalchemy import text

from aurora.config import DATA_DIR
from aurora.store.errors import SeedDataError
from aurora.store.seed import bootstrap_store, read_seed_data, reset_condo_data

FIXTURES = Path(__file__).parent / "fixtures"


async def _state(engine):
    async with engine.connect() as conn:
        reservations = (
            await conn.execute(
                text("SELECT code, apartment, area_id, day FROM reservations ORDER BY code")
            )
        ).all()
        visitors = (
            await conn.execute(text("SELECT apartment, name, day FROM visitors ORDER BY name"))
        ).all()
    return reservations, visitors


async def _insert_extra(engine):
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO reservations (apartment, area_id, day) "
                "VALUES ('101', 'quadra', '2030-04-06')"
            )
        )


async def _next_number(engine):
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT nextval('reservation_code_seq')"))).scalar_one()


def test_read_seed_data_from_dados():
    data = read_seed_data(DATA_DIR)
    assert (len(data.apartments), len(data.areas)) == (6, 3)
    assert (len(data.reservations), len(data.visitors)) == (3, 2)
    assert data.code_floor == 4821


async def test_reset_restores_initial_state(seeded):
    baseline = await _state(seeded)
    await _insert_extra(seeded)
    async with seeded.begin() as conn:
        await conn.execute(text("DELETE FROM visitors"))
        summary = await reset_condo_data(conn)
    assert (summary.reservations, summary.visitors) == (3, 2)
    assert await _state(seeded) == baseline
    assert [r[0] for r in baseline[0]] == ["RSV-1377", "RSV-2950", "RSV-4821"]


async def test_reset_is_idempotent(seeded):
    baseline = await _state(seeded)
    async with seeded.begin() as conn:
        await reset_condo_data(conn)
    assert await _state(seeded) == baseline


async def test_reset_restarts_code_sequence(seeded):
    await _insert_extra(seeded)
    async with seeded.begin() as conn:
        await reset_condo_data(conn)
    await _insert_extra(seeded)
    reservations, _ = await _state(seeded)
    assert "RSV-4822" in [r[0] for r in reservations]


async def test_reset_on_empty_database_creates_schema(empty_database):
    async with empty_database.begin() as conn:
        await reset_condo_data(conn)
    reservations, visitors = await _state(empty_database)
    assert len(reservations) == 3 and len(visitors) == 2


async def test_reset_rolled_back_changes_nothing(seeded):
    await _insert_extra(seeded)
    before = await _state(seeded)
    async with seeded.connect() as conn:
        await reset_condo_data(conn)
        await conn.rollback()
    assert await _state(seeded) == before
    assert await _next_number(seeded) > 4822


@pytest.mark.parametrize(
    ("directory", "filename"),
    [
        ("seed_malformed", "reservas.json"),
        ("seed_missing_file", "visitantes.json"),
        ("seed_inconsistent", "reservas.json"),
    ],
)
async def test_invalid_data_aborts_before_any_change(seeded, directory, filename):
    await _insert_extra(seeded)
    before = await _state(seeded)
    with pytest.raises(SeedDataError, match=filename):
        async with seeded.begin() as conn:
            await reset_condo_data(conn, FIXTURES / directory)
    assert await _state(seeded) == before


async def test_bootstrap_preserves_reservations_and_visitors(seeded):
    await _insert_extra(seeded)
    before = await _state(seeded)
    async with seeded.begin() as conn:
        await bootstrap_store(conn)
    assert await _state(seeded) == before
    assert await _next_number(seeded) > 4822


def _hashes():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA_DIR.iterdir()}


async def test_dados_files_are_untouched(empty_database):
    before = _hashes()
    async with empty_database.begin() as conn:
        await bootstrap_store(conn)
    async with empty_database.begin() as conn:
        await reset_condo_data(conn)
    assert _hashes() == before


def test_valid_copy_reads(tmp_path):
    for f in DATA_DIR.glob("*.json"):
        (tmp_path / f.name).write_bytes(f.read_bytes())
    assert read_seed_data(tmp_path).code_floor == 4821


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("areas.json", '[{"id": "x", "nome": "X", "taxa": -1}]'),
        ("areas.json", '{"id": "x"}'),
        (
            "reservas.json",
            '[{"codigo": "XYZ", "apartamento": "101", "area": "quadra", "data": "2030-01-01"}]',
        ),
        (
            "reservas.json",
            '[{"codigo": "RSV-1", "apartamento": "101", "area": "quadra", "data": "2030-02-31"}]',
        ),
        ("visitantes.json", '[{"apartamento": "101", "nome": " ", "data": "2030-01-01"}]'),
    ],
)
def test_invalid_content_is_rejected(tmp_path, filename, content):
    for f in DATA_DIR.glob("*.json"):
        (tmp_path / f.name).write_bytes(f.read_bytes())
    (tmp_path / filename).write_text(content, encoding="utf-8")
    with pytest.raises(SeedDataError, match=filename):
        read_seed_data(tmp_path)
