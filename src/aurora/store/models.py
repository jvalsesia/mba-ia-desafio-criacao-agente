import enum
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


class ReservationStatus(enum.StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"


class Availability(enum.StrEnum):
    FREE = "free"
    TAKEN = "taken"


@dataclass(frozen=True)
class Apartment:
    number: str
    resident: str


@dataclass(frozen=True)
class Area:
    id: str
    name: str
    fee: Decimal


@dataclass(frozen=True)
class Reservation:
    code: str
    apartment: str
    area_id: str
    day: date
    status: ReservationStatus


@dataclass(frozen=True)
class Visitor:
    apartment: str
    name: str
    day: date


@dataclass(frozen=True)
class SeedSummary:
    reservations: int
    visitors: int


@dataclass(frozen=True)
class DateTaken:
    """The area is already reserved on that date; says nothing about who holds it."""


@dataclass(frozen=True)
class UnknownArea:
    pass


@dataclass(frozen=True)
class ReservationNotFound:
    """Unknown code, another apartment's code or already cancelled: indistinguishable."""


@dataclass(frozen=True)
class AlreadyAuthorized:
    pass
