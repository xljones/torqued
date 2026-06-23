"""SQLAlchemy ORM models.

A thin declarative mapping over the existing schema, used by repositories that have
moved off raw SQL onto the ORM. The hand-written Alembic migrations remain the single
source of truth for the schema, so these models omit foreign keys and are *not* wired
into Alembic autogenerate — they exist only to drive DML through a
:class:`~sqlalchemy.orm.Session`.

Columns the database populates (``created_at`` timestamps, ``source``) are marked with
``server_default=FetchedValue()``: this tells the ORM to leave them out of an INSERT so
the migration's real default fires, then read the generated value back on ``refresh``.
The actual default expression lives in the migration (and is dialect-specific), so it is
deliberately not duplicated here.

Models are added here incrementally as each repository is converted.
"""
from typing import Any

from sqlalchemy import FetchedValue, Float, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def to_dict(obj: Base) -> dict[str, Any]:
    """Return a mapped row as a plain dict with the same keys ``SELECT *`` produced."""
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


class OdometerLog(Base):
    __tablename__ = "odometer_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(Integer)
    date: Mapped[str] = mapped_column(Text)
    odometer_km: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, server_default=FetchedValue())
    mot_test_number: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text, server_default=FetchedValue())
