from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from aurora.store.errors import translate_errors
from aurora.store.models import AlreadyAuthorized, Visitor
from aurora.store.schema import visitors

_COLUMNS = (visitors.c.apartment, visitors.c.name, visitors.c.day)


def normalize_name(name: str) -> str:
    return " ".join(name.split())


@translate_errors
async def create_visitor(
    engine: AsyncEngine, *, apartment: str, name: str, day: date
) -> Visitor | AlreadyAuthorized:
    stmt = (
        insert(visitors)
        .values(apartment=apartment, name=normalize_name(name), day=day)
        .on_conflict_do_nothing(
            index_elements=[visitors.c.apartment, func.lower(visitors.c.name), visitors.c.day]
        )
        .returning(*_COLUMNS)
    )
    async with engine.begin() as conn:
        row = (await conn.execute(stmt)).first()
    if row is None:
        return AlreadyAuthorized()
    return Visitor(apartment=row.apartment, name=row.name, day=row.day)


@translate_errors
async def list_visitors(engine: AsyncEngine, *, apartment: str) -> list[Visitor]:
    stmt = (
        select(*_COLUMNS)
        .where(visitors.c.apartment == apartment)
        .order_by(visitors.c.day, visitors.c.name)
    )
    async with engine.begin() as conn:
        return [Visitor(r.apartment, r.name, r.day) for r in await conn.execute(stmt)]
