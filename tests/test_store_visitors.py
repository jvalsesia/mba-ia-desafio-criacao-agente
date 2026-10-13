import asyncio
from datetime import date

from aurora.store.models import AlreadyAuthorized, Visitor
from aurora.store.visitors import create_visitor, list_visitors

DAY = date(2030, 4, 21)


async def test_create_and_list_visitor(seeded):
    result = await create_visitor(seeded, apartment="101", name="Joana Ribeiro", day=DAY)
    assert result == Visitor("101", "Joana Ribeiro", DAY)
    assert await list_visitors(seeded, apartment="101") == [result]


async def test_list_is_scoped_to_apartment(seeded):
    assert await list_visitors(seeded, apartment="302") == [
        Visitor("302", "Marina Duarte", date(2030, 3, 16))
    ]
    assert await list_visitors(seeded, apartment="101") == []


async def test_duplicate_returns_already_authorized(seeded):
    await create_visitor(seeded, apartment="101", name="Joana Ribeiro", day=DAY)
    result = await create_visitor(seeded, apartment="101", name="joana  ribeiro", day=DAY)
    assert result == AlreadyAuthorized()
    assert len(await list_visitors(seeded, apartment="101")) == 1


async def test_concurrent_duplicates_leave_one_row(seeded):
    results = await asyncio.gather(
        create_visitor(seeded, apartment="101", name="Joana Ribeiro", day=DAY),
        create_visitor(seeded, apartment="101", name="JOANA RIBEIRO", day=DAY),
    )
    assert sum(isinstance(r, Visitor) for r in results) == 1
    assert sum(isinstance(r, AlreadyAuthorized) for r in results) == 1
    assert len(await list_visitors(seeded, apartment="101")) == 1


async def test_same_name_in_another_apartment_is_allowed(seeded):
    await create_visitor(seeded, apartment="101", name="Joana Ribeiro", day=DAY)
    result = await create_visitor(seeded, apartment="201", name="Joana Ribeiro", day=DAY)
    assert isinstance(result, Visitor)
    assert len(await list_visitors(seeded, apartment="101")) == 1


async def test_name_is_normalized(seeded):
    result = await create_visitor(seeded, apartment="101", name="  Joana   Ribeiro ", day=DAY)
    assert result.name == "Joana Ribeiro"
