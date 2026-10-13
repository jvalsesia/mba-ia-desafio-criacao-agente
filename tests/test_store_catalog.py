from decimal import Decimal

from aurora.store import catalog
from aurora.store.models import Apartment, Area


async def test_list_areas_returns_three_with_fees(seeded):
    areas = await catalog.list_areas(seeded)
    fees = {a.id: a.fee for a in areas}
    assert fees == {
        "salao-de-festas": Decimal("150.00"),
        "churrasqueira": Decimal("80.00"),
        "quadra": Decimal("0"),
    }
    assert all(isinstance(a.fee, Decimal) and a.name for a in areas)
    assert [a.name for a in areas] == sorted(a.name for a in areas)


async def test_get_area_known_and_unknown(seeded):
    assert await catalog.get_area(seeded, area_id="quadra") == Area(
        "quadra", "Quadra poliesportiva", Decimal("0")
    )
    assert await catalog.get_area(seeded, area_id="piscina") is None


async def test_get_apartment_known_and_unknown(seeded):
    assert await catalog.get_apartment(seeded, number="101") == Apartment("101", "Helena Prado")
    assert await catalog.get_apartment(seeded, number="999") is None


async def test_sync_catalog_is_idempotent(seeded):
    from aurora.store.seed import read_seed_data

    data = read_seed_data()
    for _ in range(2):
        async with seeded.begin() as conn:
            await catalog.sync_catalog(conn, data.apartments, data.areas)
    assert len(await catalog.list_areas(seeded)) == 3
    for number in ("101", "102", "201", "202", "301", "302"):
        assert await catalog.get_apartment(seeded, number=number) is not None
    async with seeded.connect() as conn:
        from sqlalchemy import func, select

        from aurora.store.schema import apartments

        assert (await conn.execute(select(func.count()).select_from(apartments))).scalar_one() == 6
