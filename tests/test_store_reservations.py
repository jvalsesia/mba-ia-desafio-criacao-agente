import asyncio
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from aurora.store.errors import StoreError
from aurora.store.models import (
    Availability,
    DateTaken,
    Reservation,
    ReservationNotFound,
    ReservationStatus,
    UnknownArea,
)
from aurora.store.reservations import (
    cancel_reservation,
    check_availability,
    create_reservation,
    list_reservations,
)

INITIAL = {"RSV-1377", "RSV-4821", "RSV-2950"}


async def _codes(engine, apartment):
    return [r.code for r in await list_reservations(engine, apartment=apartment)]


def _number(code: str) -> int:
    return int(code.removeprefix("RSV-"))


async def test_create_on_free_date(seeded):
    result = await create_reservation(
        seeded, apartment="101", area_id="quadra", day=date(2030, 4, 6)
    )
    assert isinstance(result, Reservation)
    assert result.status is ReservationStatus.ACTIVE
    assert (result.apartment, result.area_id, result.day) == ("101", "quadra", date(2030, 4, 6))
    assert _number(result.code) > 4821
    assert result.code in await _codes(seeded, "101")


async def test_create_on_taken_date_returns_date_taken(seeded):
    result = await create_reservation(
        seeded, apartment="101", area_id="salao-de-festas", day=date(2030, 3, 16)
    )
    assert result == DateTaken()
    assert await _codes(seeded, "101") == ["RSV-1377"]
    assert await _codes(seeded, "302") == ["RSV-4821"]


async def test_concurrent_creates_have_one_winner(seeded):
    for n in range(10):
        day = date(2030, 5, 11 + n)
        results = await asyncio.gather(
            create_reservation(seeded, apartment="101", area_id="salao-de-festas", day=day),
            create_reservation(seeded, apartment="201", area_id="salao-de-festas", day=day),
        )
        assert sum(isinstance(r, Reservation) for r in results) == 1
        assert sum(isinstance(r, DateTaken) for r in results) == 1
    total = [
        r
        for apt in ("101", "201")
        for r in await list_reservations(seeded, apartment=apt)
        if r.area_id == "salao-de-festas"
    ]
    assert len(total) == 10


async def test_cancelled_reservation_frees_the_date(seeded):
    await cancel_reservation(seeded, apartment="101", code="RSV-1377")
    result = await create_reservation(
        seeded, apartment="201", area_id="quadra", day=date(2030, 3, 9)
    )
    assert isinstance(result, Reservation) and result.code != "RSV-1377"
    assert "RSV-1377" not in await _codes(seeded, "101")


async def test_create_unknown_area(seeded):
    result = await create_reservation(
        seeded, apartment="101", area_id="piscina", day=date(2030, 4, 6)
    )
    assert result == UnknownArea()
    assert await _codes(seeded, "101") == ["RSV-1377"]


async def test_create_unknown_apartment_raises_store_error(seeded):
    with pytest.raises(StoreError):
        await create_reservation(seeded, apartment="999", area_id="quadra", day=date(2030, 4, 6))
    assert (
        await check_availability(seeded, area_id="quadra", day=date(2030, 4, 6))
        is Availability.FREE
    )


async def test_codes_stay_distinct_after_twenty_cycles(seeded):
    codes = []
    for _ in range(20):
        created = await create_reservation(
            seeded, apartment="101", area_id="quadra", day=date(2030, 6, 1)
        )
        assert isinstance(created, Reservation)
        codes.append(created.code)
        assert isinstance(
            await cancel_reservation(seeded, apartment="101", code=created.code), Reservation
        )
    assert len(set(codes) | INITIAL) == 23


async def test_cancel_own_reservation(seeded):
    result = await cancel_reservation(seeded, apartment="101", code="RSV-1377")
    assert isinstance(result, Reservation) and result.status is ReservationStatus.CANCELLED
    assert await _codes(seeded, "101") == []
    async with seeded.connect() as conn:
        from sqlalchemy import text

        row = (
            await conn.execute(
                text("SELECT status, cancelled_at FROM reservations WHERE code = 'RSV-1377'")
            )
        ).one()
    assert row.status == "cancelled" and row.cancelled_at is not None


async def test_cancel_foreign_and_unknown_codes_are_not_found(seeded):
    foreign = await cancel_reservation(seeded, apartment="101", code="RSV-4821")
    unknown = await cancel_reservation(seeded, apartment="101", code="RSV-9999")
    assert foreign == unknown == ReservationNotFound()
    assert await _codes(seeded, "302") == ["RSV-4821"]
    assert (
        await check_availability(seeded, area_id="salao-de-festas", day=date(2030, 3, 16))
        is Availability.TAKEN
    )


async def test_cancel_twice_is_not_found(seeded):
    await cancel_reservation(seeded, apartment="101", code="RSV-1377")
    assert (
        await cancel_reservation(seeded, apartment="101", code="RSV-1377") == ReservationNotFound()
    )
    assert await _codes(seeded, "101") == []


async def test_list_is_scoped_active_and_ordered(seeded):
    await create_reservation(
        seeded, apartment="101", area_id="salao-de-festas", day=date(2030, 4, 20)
    )
    await create_reservation(seeded, apartment="101", area_id="quadra", day=date(2030, 4, 6))
    await cancel_reservation(seeded, apartment="101", code="RSV-1377")
    listed = await list_reservations(seeded, apartment="101")
    assert [(r.area_id, r.day) for r in listed] == [
        ("quadra", date(2030, 4, 6)),
        ("salao-de-festas", date(2030, 4, 20)),
    ]


async def test_list_for_apartment_without_reservations(seeded):
    assert await list_reservations(seeded, apartment="102") == []


async def test_availability_taken_and_free(seeded):
    day = date(2030, 3, 16)
    assert (
        await check_availability(seeded, area_id="salao-de-festas", day=day) is Availability.TAKEN
    )
    assert (
        await check_availability(seeded, area_id="salao-de-festas", day=date(2030, 4, 20))
        is Availability.FREE
    )


async def test_availability_after_cancel_is_free(seeded):
    await cancel_reservation(seeded, apartment="101", code="RSV-1377")
    assert (
        await check_availability(seeded, area_id="quadra", day=date(2030, 3, 9))
        is Availability.FREE
    )


async def test_availability_unknown_area(seeded):
    assert (
        await check_availability(seeded, area_id="piscina", day=date(2030, 4, 6)) == UnknownArea()
    )


async def test_unreachable_database_raises_store_error():
    engine = create_async_engine("postgresql+asyncpg://aurora:segredo-teste@localhost:5999/aurora")
    try:
        with pytest.raises(StoreError) as info:
            await list_reservations(engine, apartment="101")
    finally:
        await engine.dispose()
    message = str(info.value)
    assert "segredo-teste" not in message and "SELECT" not in message.upper()
