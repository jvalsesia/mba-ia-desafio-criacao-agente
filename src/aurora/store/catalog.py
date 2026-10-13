from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aurora.store.errors import translate_errors
from aurora.store.models import Apartment, Area
from aurora.store.schema import apartments, areas


@translate_errors
async def list_areas(engine: AsyncEngine) -> list[Area]:
    async with engine.begin() as conn:
        rows = await conn.execute(
            select(areas.c.id, areas.c.name, areas.c.fee).order_by(areas.c.name)
        )
        return [Area(id=r.id, name=r.name, fee=Decimal(r.fee)) for r in rows]


@translate_errors
async def get_area(engine: AsyncEngine, *, area_id: str) -> Area | None:
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                select(areas.c.id, areas.c.name, areas.c.fee).where(areas.c.id == area_id)
            )
        ).one_or_none()
    return None if row is None else Area(id=row.id, name=row.name, fee=Decimal(row.fee))


@translate_errors
async def get_apartment(engine: AsyncEngine, *, number: str) -> Apartment | None:
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                select(apartments.c.number, apartments.c.resident).where(
                    apartments.c.number == number
                )
            )
        ).one_or_none()
    return None if row is None else Apartment(number=row.number, resident=row.resident)


async def sync_catalog(
    conn: AsyncConnection, apartment_rows: Sequence[Apartment], area_rows: Sequence[Area]
) -> None:
    """Upsert by primary key; never removes rows."""
    if apartment_rows:
        stmt = insert(apartments).values(
            [{"number": a.number, "resident": a.resident} for a in apartment_rows]
        )
        await conn.execute(
            stmt.on_conflict_do_update(
                index_elements=[apartments.c.number], set_={"resident": stmt.excluded.resident}
            )
        )
    if area_rows:
        stmt = insert(areas).values([{"id": a.id, "name": a.name, "fee": a.fee} for a in area_rows])
        await conn.execute(
            stmt.on_conflict_do_update(
                index_elements=[areas.c.id],
                set_={"name": stmt.excluded.name, "fee": stmt.excluded.fee},
            )
        )
