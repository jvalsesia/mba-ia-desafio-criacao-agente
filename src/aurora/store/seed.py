import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from aurora.config import DATA_DIR
from aurora.store.catalog import sync_catalog
from aurora.store.errors import SeedDataError, translate_errors
from aurora.store.models import (
    Apartment,
    Area,
    Reservation,
    ReservationStatus,
    SeedSummary,
    Visitor,
)
from aurora.store.schema import ensure_schema, reservations, visitors

CODE_PATTERN = re.compile(r"RSV-(\d+)")

APARTMENTS_FILE = "apartamentos.json"
AREAS_FILE = "areas.json"
RESERVATIONS_FILE = "reservas.json"
VISITORS_FILE = "visitantes.json"


@dataclass(frozen=True)
class SeedData:
    apartments: list[Apartment]
    areas: list[Area]
    reservations: list[Reservation]
    visitors: list[Visitor]
    code_floor: int


def _load_list(data_dir: Path, filename: str) -> list[dict]:
    path = data_dir / filename
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SeedDataError(filename, "arquivo ausente") from None
    except (OSError, UnicodeDecodeError):
        raise SeedDataError(filename, "arquivo ilegível") from None
    except json.JSONDecodeError:
        raise SeedDataError(filename, "JSON inválido") from None
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise SeedDataError(filename, "esperada uma lista de objetos")
    return raw


def _text(item: dict, key: str, filename: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SeedDataError(filename, f"campo '{key}' ausente ou vazio")
    return value


def _day(item: dict, filename: str) -> date:
    value = _text(item, "data", filename)
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise SeedDataError(filename, f"data inválida '{value}'") from None


def _unique(seen: set, key, filename: str, what: str) -> None:
    if key in seen:
        raise SeedDataError(filename, f"{what} duplicado")
    seen.add(key)


def read_seed_data(data_dir: Path = DATA_DIR) -> SeedData:
    """Read and validate the four files without touching the database."""
    apartment_rows: list[Apartment] = []
    numbers: set[str] = set()
    for item in _load_list(data_dir, APARTMENTS_FILE):
        number = _text(item, "numero", APARTMENTS_FILE)
        _unique(numbers, number, APARTMENTS_FILE, f"apartamento '{number}'")
        apartment_rows.append(Apartment(number, _text(item, "morador", APARTMENTS_FILE)))

    area_rows: list[Area] = []
    area_ids: set[str] = set()
    for item in _load_list(data_dir, AREAS_FILE):
        area_id = _text(item, "id", AREAS_FILE)
        _unique(area_ids, area_id, AREAS_FILE, f"id de área '{area_id}'")
        raw_fee = item.get("taxa")
        try:
            fee = Decimal(str(raw_fee))
        except InvalidOperation:
            fee = Decimal(-1)
        if isinstance(raw_fee, bool) or not fee.is_finite() or fee < 0:
            raise SeedDataError(AREAS_FILE, "campo 'taxa' deve ser um número maior ou igual a zero")
        area_rows.append(Area(area_id, _text(item, "nome", AREAS_FILE), fee))

    reservation_rows: list[Reservation] = []
    codes: set[str] = set()
    area_days: set[tuple[str, date]] = set()
    code_floor = 0
    for item in _load_list(data_dir, RESERVATIONS_FILE):
        code = _text(item, "codigo", RESERVATIONS_FILE)
        match = CODE_PATTERN.fullmatch(code)
        if not match:
            raise SeedDataError(RESERVATIONS_FILE, f"código '{code}' fora do formato RSV-<número>")
        _unique(codes, code, RESERVATIONS_FILE, f"código '{code}'")
        apartment = _text(item, "apartamento", RESERVATIONS_FILE)
        if apartment not in numbers:
            raise SeedDataError(RESERVATIONS_FILE, f"apartamento '{apartment}' inexistente")
        area_id = _text(item, "area", RESERVATIONS_FILE)
        if area_id not in area_ids:
            raise SeedDataError(RESERVATIONS_FILE, f"área '{area_id}' inexistente")
        day = _day(item, RESERVATIONS_FILE)
        _unique(area_days, (area_id, day), RESERVATIONS_FILE, f"par área e data ({area_id}, {day})")
        code_floor = max(code_floor, int(match.group(1)))
        reservation_rows.append(
            Reservation(code, apartment, area_id, day, ReservationStatus.ACTIVE)
        )

    visitor_rows: list[Visitor] = []
    trios: set[tuple[str, str, date]] = set()
    for item in _load_list(data_dir, VISITORS_FILE):
        apartment = _text(item, "apartamento", VISITORS_FILE)
        if apartment not in numbers:
            raise SeedDataError(VISITORS_FILE, f"apartamento '{apartment}' inexistente")
        name = " ".join(_text(item, "nome", VISITORS_FILE).split())
        day = _day(item, VISITORS_FILE)
        _unique(trios, (apartment, name.lower(), day), VISITORS_FILE, f"visitante '{name}'")
        visitor_rows.append(Visitor(apartment, name, day))

    return SeedData(apartment_rows, area_rows, reservation_rows, visitor_rows, code_floor)


@translate_errors
async def bootstrap_store(conn: AsyncConnection, data_dir: Path = DATA_DIR) -> None:
    """Create the schema and sync the catalog; reservations and visitors are left alone."""
    data = read_seed_data(data_dir)
    await ensure_schema(conn, data.code_floor)
    await sync_catalog(conn, data.apartments, data.areas)


async def bootstrap_database(url: str, data_dir: Path = DATA_DIR) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await bootstrap_store(conn, data_dir)
    finally:
        await engine.dispose()


@translate_errors
async def reset_condo_data(conn: AsyncConnection, data_dir: Path = DATA_DIR) -> SeedSummary:
    """Restore reservations, visitors and the code sequence; the caller owns the transaction."""
    data = read_seed_data(data_dir)
    await ensure_schema(conn, data.code_floor)
    await sync_catalog(conn, data.apartments, data.areas)
    await conn.execute(delete(reservations))
    await conn.execute(delete(visitors))
    if data.reservations:
        await conn.execute(
            reservations.insert(),
            [
                {"code": r.code, "apartment": r.apartment, "area_id": r.area_id, "day": r.day}
                for r in data.reservations
            ],
        )
    if data.visitors:
        await conn.execute(
            visitors.insert(),
            [{"apartment": v.apartment, "name": v.name, "day": v.day} for v in data.visitors],
        )
    await conn.execute(
        text(f"ALTER SEQUENCE reservation_code_seq RESTART WITH {data.code_floor + 1}")
    )
    return SeedSummary(reservations=len(data.reservations), visitors=len(data.visitors))
