from datetime import date

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from aurora.store.errors import translate_errors
from aurora.store.models import (
    Availability,
    DateTaken,
    Reservation,
    ReservationNotFound,
    ReservationStatus,
    UnknownArea,
)
from aurora.store.schema import areas, reservations

_COLUMNS = (
    reservations.c.code,
    reservations.c.apartment,
    reservations.c.area_id,
    reservations.c.day,
    reservations.c.status,
)


def _to_reservation(row) -> Reservation:
    return Reservation(
        code=row.code,
        apartment=row.apartment,
        area_id=row.area_id,
        day=row.day,
        status=ReservationStatus(row.status),
    )


async def _area_exists(conn, area_id: str) -> bool:
    found = await conn.execute(select(areas.c.id).where(areas.c.id == area_id))
    return found.first() is not None


@translate_errors
async def create_reservation(
    engine: AsyncEngine, *, apartment: str, area_id: str, day: date
) -> Reservation | DateTaken | UnknownArea:
    async with engine.begin() as conn:
        if not await _area_exists(conn, area_id):
            return UnknownArea()
        stmt = (
            insert(reservations)
            .values(apartment=apartment, area_id=area_id, day=day)
            .on_conflict_do_nothing(
                index_elements=[reservations.c.area_id, reservations.c.day],
                index_where=text("status = 'active'"),
            )
            .returning(*_COLUMNS)
        )
        row = (await conn.execute(stmt)).first()
    return DateTaken() if row is None else _to_reservation(row)


@translate_errors
async def cancel_reservation(
    engine: AsyncEngine, *, apartment: str, code: str
) -> Reservation | ReservationNotFound:
    stmt = (
        update(reservations)
        .where(
            reservations.c.code == code,
            reservations.c.apartment == apartment,
            reservations.c.status == ReservationStatus.ACTIVE.value,
        )
        .values(status=ReservationStatus.CANCELLED.value, cancelled_at=func.now())
        .returning(*_COLUMNS)
    )
    async with engine.begin() as conn:
        row = (await conn.execute(stmt)).first()
    return ReservationNotFound() if row is None else _to_reservation(row)


@translate_errors
async def list_reservations(engine: AsyncEngine, *, apartment: str) -> list[Reservation]:
    stmt = (
        select(*_COLUMNS)
        .where(
            reservations.c.apartment == apartment,
            reservations.c.status == ReservationStatus.ACTIVE.value,
        )
        .order_by(reservations.c.day, reservations.c.code)
    )
    async with engine.begin() as conn:
        return [_to_reservation(row) for row in await conn.execute(stmt)]


@translate_errors
async def check_availability(
    engine: AsyncEngine, *, area_id: str, day: date
) -> Availability | UnknownArea:
    taken = (
        select(reservations.c.code)
        .where(
            reservations.c.area_id == area_id,
            reservations.c.day == day,
            reservations.c.status == ReservationStatus.ACTIVE.value,
        )
        .exists()
    )
    async with engine.begin() as conn:
        if not await _area_exists(conn, area_id):
            return UnknownArea()
        is_taken = (await conn.execute(select(taken))).scalar_one()
    return Availability.TAKEN if is_taken else Availability.FREE
