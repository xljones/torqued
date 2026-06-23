"""SQLAlchemy ORM models.

A thin declarative mapping over the existing schema, used by the repositories. The
hand-written Alembic migrations remain the single source of truth for the schema, so
these models omit foreign keys and are *not* wired into Alembic autogenerate — they exist
only to drive DML and queries through a :class:`~sqlalchemy.orm.Session`.

Columns the database populates (``created_at``/``updated_at`` timestamps and the various
``server_default`` columns) are marked with ``server_default=FetchedValue()``: this tells
the ORM to leave them out of an INSERT so the migration's real default fires, then read
the generated value back on ``refresh``. The actual default expression lives in the
migration (and is dialect-specific), so it is deliberately not duplicated here.

Every column of each table is mapped, so ``to_dict`` reproduces the old ``SELECT *`` shape.
"""
from typing import Any

from sqlalchemy import FetchedValue, Float, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def to_dict(obj: Base) -> dict[str, Any]:
    """Return a mapped row as a plain dict with the same keys ``SELECT *`` produced."""
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    is_admin: Mapped[int] = mapped_column(Integer, server_default=FetchedValue())
    expires_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text, server_default=FetchedValue())


class Garage(Base):
    __tablename__ = "garages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text, server_default=FetchedValue())


class GarageMember(Base):
    __tablename__ = "garage_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    garage_id: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(Text, server_default=FetchedValue())
    created_at: Mapped[str | None] = mapped_column(Text, server_default=FetchedValue())


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    garage_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, server_default=FetchedValue())
    make: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    registration: Mapped[str | None] = mapped_column(Text)
    vin: Mapped[str | None] = mapped_column(Text)
    colour: Mapped[str | None] = mapped_column(Text)
    fuel_type: Mapped[str | None] = mapped_column(Text)
    engine_size: Mapped[str | None] = mapped_column(Text)
    first_used_date: Mapped[str | None] = mapped_column(Text)
    registration_date: Mapped[str | None] = mapped_column(Text)
    odometer_unit: Mapped[str] = mapped_column(Text, server_default=FetchedValue())
    purchase_date: Mapped[str | None] = mapped_column(Text)
    tyre_size_front: Mapped[str | None] = mapped_column(Text)
    tyre_size_rear: Mapped[str | None] = mapped_column(Text)
    tyre_pressure_front_psi: Mapped[float | None] = mapped_column(Float)
    tyre_pressure_rear_psi: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    archived: Mapped[int] = mapped_column(Integer, server_default=FetchedValue())
    created_at: Mapped[str | None] = mapped_column(Text, server_default=FetchedValue())
    updated_at: Mapped[str | None] = mapped_column(Text, server_default=FetchedValue())


class VehicleSpec(Base):
    __tablename__ = "vehicle_specs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)
    value: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, server_default=FetchedValue())
    created_at: Mapped[str | None] = mapped_column(Text, server_default=FetchedValue())


class VehicleHistory(Base):
    __tablename__ = "vehicle_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(Integer)
    changed_at: Mapped[str | None] = mapped_column(Text, server_default=FetchedValue())
    changed_by: Mapped[int | None] = mapped_column(Integer)
    name: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str | None] = mapped_column(Text)
    make: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    registration: Mapped[str | None] = mapped_column(Text)
    vin: Mapped[str | None] = mapped_column(Text)
    colour: Mapped[str | None] = mapped_column(Text)
    fuel_type: Mapped[str | None] = mapped_column(Text)
    engine_size: Mapped[str | None] = mapped_column(Text)
    first_used_date: Mapped[str | None] = mapped_column(Text)
    registration_date: Mapped[str | None] = mapped_column(Text)
    odometer_unit: Mapped[str | None] = mapped_column(Text)
    purchase_date: Mapped[str | None] = mapped_column(Text)
    tyre_size_front: Mapped[str | None] = mapped_column(Text)
    tyre_size_rear: Mapped[str | None] = mapped_column(Text)
    tyre_pressure_front_psi: Mapped[float | None] = mapped_column(Float)
    tyre_pressure_rear_psi: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    archived: Mapped[int | None] = mapped_column(Integer)


class ServiceLog(Base):
    __tablename__ = "service_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(Integer)
    date: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    performed_by: Mapped[str | None] = mapped_column(Text)
    cost: Mapped[float | None] = mapped_column(Float)
    odometer_km: Mapped[float | None] = mapped_column(Float)
    odometer_unit: Mapped[str | None] = mapped_column(Text)
    next_due_date: Mapped[str | None] = mapped_column(Text)
    next_due_km: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[str | None] = mapped_column(Text, server_default=FetchedValue())
    updated_at: Mapped[str | None] = mapped_column(Text, server_default=FetchedValue())


class ServiceLogFaultCode(Base):
    __tablename__ = "service_log_fault_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_log_id: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(Text)


class ServiceLogHistory(Base):
    __tablename__ = "service_log_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_log_id: Mapped[int] = mapped_column(Integer)
    changed_at: Mapped[str | None] = mapped_column(Text, server_default=FetchedValue())
    changed_by: Mapped[int | None] = mapped_column(Integer)
    vehicle_id: Mapped[int | None] = mapped_column(Integer)
    date: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    performed_by: Mapped[str | None] = mapped_column(Text)
    cost: Mapped[float | None] = mapped_column(Float)
    odometer_km: Mapped[float | None] = mapped_column(Float)
    odometer_unit: Mapped[str | None] = mapped_column(Text)
    next_due_date: Mapped[str | None] = mapped_column(Text)
    next_due_km: Mapped[float | None] = mapped_column(Float)


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


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(Integer)
    service_log_id: Mapped[int | None] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(Text)
    original_name: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str | None] = mapped_column(Text, server_default=FetchedValue())


class DvsaVehicle(Base):
    __tablename__ = "dvsa_vehicles"

    # Migration 0002 made `id` the surrogate primary key and `vehicle_id` a nullable
    # FK (ON DELETE SET NULL), so a DVSA record survives its vehicle's deletion as a
    # detached row (vehicle_id IS NULL).
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vehicle_id: Mapped[int | None] = mapped_column(Integer)
    registration: Mapped[str | None] = mapped_column(Text)
    make: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    first_used_date: Mapped[str | None] = mapped_column(Text)
    fuel_type: Mapped[str | None] = mapped_column(Text)
    primary_colour: Mapped[str | None] = mapped_column(Text)
    registration_date: Mapped[str | None] = mapped_column(Text)
    manufacture_date: Mapped[str | None] = mapped_column(Text)
    manufacture_year: Mapped[int | None] = mapped_column(Integer)
    engine_size: Mapped[str | None] = mapped_column(Text)
    has_outstanding_recall: Mapped[str | None] = mapped_column(Text)
    mot_test_due_date: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[str | None] = mapped_column(Text, server_default=FetchedValue())


class MotTest(Base):
    __tablename__ = "mot_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(Integer)
    completed_date: Mapped[str] = mapped_column(Text)
    test_result: Mapped[str | None] = mapped_column(Text)
    expiry_date: Mapped[str | None] = mapped_column(Text)
    odometer_value: Mapped[int | None] = mapped_column(Integer)
    odometer_unit: Mapped[str | None] = mapped_column(Text)
    odometer_result_type: Mapped[str | None] = mapped_column(Text)
    mot_test_number: Mapped[str | None] = mapped_column(Text)
    data_source: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    defects_json: Mapped[str] = mapped_column(Text, server_default=FetchedValue())
    raw_json: Mapped[str] = mapped_column(Text)
