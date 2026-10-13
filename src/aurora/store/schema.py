from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Identity,
    Index,
    MetaData,
    Numeric,
    PrimaryKeyConstraint,
    Sequence,
    String,
    Table,
    func,
    text,
)
from sqlalchemy.ext.asyncio import AsyncConnection

metadata = MetaData()

SCHEMA_LOCK_KEY = 7_204_001

reservation_code_seq = Sequence("reservation_code_seq", metadata=metadata)

apartments = Table(
    "apartments",
    metadata,
    Column("number", String(10), nullable=False),
    Column("resident", String(120), nullable=False),
    PrimaryKeyConstraint("number", name="pk_apartments"),
)

areas = Table(
    "areas",
    metadata,
    Column("id", String(40), nullable=False),
    Column("name", String(80), nullable=False),
    Column("fee", Numeric(10, 2), nullable=False),
    PrimaryKeyConstraint("id", name="pk_areas"),
    CheckConstraint("fee >= 0", name="ck_areas_fee_non_negative"),
)

reservations = Table(
    "reservations",
    metadata,
    Column(
        "code",
        String(20),
        nullable=False,
        server_default=text("'RSV-' || nextval('reservation_code_seq')"),
    ),
    Column("apartment", String(10), nullable=False),
    Column("area_id", String(40), nullable=False),
    Column("day", Date, nullable=False),
    Column("status", String(10), nullable=False, server_default=text("'active'")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("cancelled_at", DateTime(timezone=True), nullable=True),
    PrimaryKeyConstraint("code", name="pk_reservations"),
    ForeignKeyConstraint(["apartment"], ["apartments.number"], name="fk_reservations_apartment"),
    ForeignKeyConstraint(["area_id"], ["areas.id"], name="fk_reservations_area"),
    CheckConstraint("status IN ('active', 'cancelled')", name="ck_reservations_status"),
)

Index(
    "uq_reservations_active_area_day",
    reservations.c.area_id,
    reservations.c.day,
    unique=True,
    postgresql_where=text("status = 'active'"),
)
Index("ix_reservations_apartment_day", reservations.c.apartment, reservations.c.day)

visitors = Table(
    "visitors",
    metadata,
    Column("id", BigInteger, Identity(always=False), nullable=False),
    Column("apartment", String(10), nullable=False),
    Column("name", String(100), nullable=False),
    Column("day", Date, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    PrimaryKeyConstraint("id", name="pk_visitors"),
    ForeignKeyConstraint(["apartment"], ["apartments.number"], name="fk_visitors_apartment"),
)

Index(
    "uq_visitors_apartment_name_day",
    visitors.c.apartment,
    func.lower(visitors.c.name),
    visitors.c.day,
    unique=True,
)


async def ensure_schema(conn: AsyncConnection, code_floor: int = 0) -> None:
    """Create whatever is missing and raise the code sequence to code_floor, never lowering it."""
    await conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SCHEMA_LOCK_KEY})
    await conn.run_sync(metadata.create_all)
    if code_floor >= 1:
        await conn.execute(
            text(
                "SELECT setval('reservation_code_seq', :floor, true) "
                "WHERE (SELECT CASE WHEN is_called THEN last_value ELSE last_value - 1 END "
                "FROM reservation_code_seq) < :floor"
            ),
            {"floor": code_floor},
        )
