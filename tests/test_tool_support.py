from datetime import date

import pytest

from aurora.agents.tool_support import (
    MSG_SERVICE_UNAVAILABLE,
    SERVICE_UNAVAILABLE,
    apartment_of,
    parse_date,
    refusal,
    safe,
    unavailable,
)
from aurora.store.errors import StoreError


def test_parse_date_accepts_strict_format():
    assert parse_date("2030-04-21") == date(2030, 4, 21)


@pytest.mark.parametrize("value", ["21/04/2030", "2030-02-30", "2030-4-6", "20300421", ""])
def test_parse_date_rejects_other_formats(value):
    assert parse_date(value) is None


def test_refusal_has_status_and_message():
    assert refusal("x", "y") == {"status": "x", "mensagem": "y"}


def test_unavailable_is_the_fixed_refusal():
    assert unavailable() == {"status": SERVICE_UNAVAILABLE, "mensagem": MSG_SERVICE_UNAVAILABLE}


async def test_safe_returns_the_result():
    async def work():
        return {"status": "ok"}

    assert await safe(work()) == {"status": "ok"}


async def test_safe_turns_store_error_into_result():
    async def work():
        raise StoreError("down")

    assert await safe(work()) == unavailable()


async def test_safe_does_not_hide_other_errors():
    async def work():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        await safe(work())


async def test_apartment_of_reads_session_state(empty_session, tool_context_for):
    assert apartment_of(tool_context_for(empty_session)) == "101"
    assert apartment_of(tool_context_for(empty_session, state={})) is None
