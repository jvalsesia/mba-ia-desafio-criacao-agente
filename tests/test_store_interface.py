import dataclasses
import inspect

import pytest

from aurora.store import catalog, reservations, visitors
from aurora.store.models import Availability, DateTaken, ReservationNotFound

SCOPED = [reservations.list_reservations, reservations.cancel_reservation, visitors.list_visitors]


@pytest.mark.parametrize("func", SCOPED)
async def test_list_and_cancel_require_apartment(func):
    param = inspect.signature(func).parameters["apartment"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        await func(None)  # type: ignore[call-arg]


def test_no_operation_lists_across_apartments():
    public = {
        f"{module.__name__}.{name}": fn
        for module in (reservations, visitors, catalog)
        for name, fn in inspect.getmembers(module, inspect.iscoroutinefunction)
        if not name.startswith("_") and fn.__module__ == module.__name__
    }
    for name, fn in public.items():
        params = inspect.signature(fn).parameters
        returns_listing = name.rsplit(".", 1)[1].startswith("list_")
        if returns_listing and name != "aurora.store.catalog.list_areas":
            assert "apartment" in params, name
    assert not any("list_apartments" in name for name in public)


def test_date_taken_and_not_found_carry_no_data():
    assert dataclasses.fields(DateTaken) == ()
    assert dataclasses.fields(ReservationNotFound) == ()


def test_availability_has_exactly_two_values():
    assert {m.value for m in Availability} == {"free", "taken"}
