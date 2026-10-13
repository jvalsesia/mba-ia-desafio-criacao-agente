from sqlalchemy import text

from aurora.store.schema import ensure_schema


async def _scalar(engine, sql, **params):
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).scalar_one()


async def _prepare(engine, floor=0):
    async with engine.begin() as conn:
        await ensure_schema(conn, floor)


async def _next_code_number(engine):
    return await _scalar(engine, "SELECT nextval('reservation_code_seq')")


async def test_ensure_schema_creates_everything_on_empty_database(empty_database):
    await _prepare(empty_database)
    tables = await _scalar(
        empty_database,
        "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' "
        "AND tablename IN ('apartments', 'areas', 'reservations', 'visitors')",
    )
    indexes = await _scalar(
        empty_database,
        "SELECT count(*) FROM pg_indexes WHERE indexname IN "
        "('uq_reservations_active_area_day', 'ix_reservations_apartment_day', "
        "'uq_visitors_apartment_name_day')",
    )
    sequence = await _scalar(
        empty_database,
        "SELECT count(*) FROM pg_sequences WHERE sequencename = 'reservation_code_seq'",
    )
    assert (tables, indexes, sequence) == (4, 3, 1)


async def test_ensure_schema_is_idempotent(empty_database):
    await _prepare(empty_database)
    async with empty_database.begin() as conn:
        await conn.execute(text("INSERT INTO apartments VALUES ('101', 'Helena')"))
    await _prepare(empty_database)
    assert await _scalar(empty_database, "SELECT count(*) FROM apartments") == 1


async def test_active_index_is_partial(empty_database):
    await _prepare(empty_database)
    definition = await _scalar(
        empty_database,
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_reservations_active_area_day'",
    )
    assert "UNIQUE" in definition
    assert "(area_id, day)" in definition
    assert "status" in definition and "'active'" in definition.split("WHERE")[1]


async def test_sequence_is_raised_to_floor(empty_database):
    await _prepare(empty_database, 4821)
    assert await _next_code_number(empty_database) == 4822


async def test_sequence_is_never_lowered(empty_database):
    await _prepare(empty_database, 4821)
    await _scalar(empty_database, "SELECT setval('reservation_code_seq', 6000)")
    await _prepare(empty_database, 4821)
    assert await _next_code_number(empty_database) == 6001
