"""retain DVSA records when their vehicle is deleted

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-23

Originally ``dvsa_vehicles.vehicle_id`` was both the primary key and a foreign key
to ``vehicles(id)`` with ``ON DELETE CASCADE`` — so deleting a vehicle also deleted
its stored DVSA snapshot. We now want to keep the DVSA record after its vehicle is
gone, so this migration restructures the table:

* a surrogate autoincrement ``id`` becomes the primary key;
* ``vehicle_id`` becomes a nullable foreign key with ``ON DELETE SET NULL`` plus a
  ``UNIQUE`` constraint (NULLs are distinct on both Postgres and SQLite, so any
  number of detached rows coexist while at most one *live* row exists per vehicle).

When a vehicle is deleted its DVSA row survives with ``vehicle_id = NULL`` — an
unambiguous "detached" marker. Nothing is lost: ``raw_json`` already holds the
complete DVSA payload (including the MOT tests array), so even though the normalized
``mot_tests`` rows still cascade away with the vehicle, the record is reconstructible.

The table is rebuilt by hand (rename → create → copy → drop) rather than via
``ALTER``: SQLite (the test backend) cannot drop/alter constraints in place, and a
plain rebuild is identical on both backends. The new ``id`` auto-populates on the
copy (SQLite INTEGER PRIMARY KEY rowid alias / Postgres identity sequence).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Columns carried across the rebuild, in declaration order (everything except the
# primary key, which is reassigned by the destination table).
_CARRIED_COLUMNS = (
    "vehicle_id",
    "registration",
    "make",
    "model",
    "first_used_date",
    "fuel_type",
    "primary_colour",
    "registration_date",
    "manufacture_date",
    "manufacture_year",
    "engine_size",
    "has_outstanding_recall",
    "mot_test_due_date",
    "raw_json",
    "fetched_at",
)


def _timestamp_default() -> sa.TextClause:
    """A server default producing a UTC `YYYY-MM-DD HH:MM:SS` text timestamp."""
    if op.get_bind().dialect.name == "postgresql":
        return sa.text("to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')")
    return sa.text("CURRENT_TIMESTAMP")


def _copy(columns: Sequence[str], source: str) -> None:
    cols = ", ".join(columns)
    op.execute(f"INSERT INTO dvsa_vehicles ({cols}) SELECT {cols} FROM {source}")


def upgrade() -> None:
    ts = _timestamp_default()

    op.rename_table("dvsa_vehicles", "_dvsa_vehicles_old")
    op.create_table(
        "dvsa_vehicles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "vehicle_id",
            sa.Integer,
            sa.ForeignKey("vehicles.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
        ),
        sa.Column("registration", sa.Text),
        sa.Column("make", sa.Text),
        sa.Column("model", sa.Text),
        sa.Column("first_used_date", sa.Text),
        sa.Column("fuel_type", sa.Text),
        sa.Column("primary_colour", sa.Text),
        sa.Column("registration_date", sa.Text),
        sa.Column("manufacture_date", sa.Text),
        sa.Column("manufacture_year", sa.Integer),
        sa.Column("engine_size", sa.Text),
        sa.Column("has_outstanding_recall", sa.Text),
        sa.Column("mot_test_due_date", sa.Text),
        sa.Column("raw_json", sa.Text, nullable=False),
        sa.Column("fetched_at", sa.Text, server_default=ts),
    )
    _copy(_CARRIED_COLUMNS, "_dvsa_vehicles_old")
    op.drop_table("_dvsa_vehicles_old")


def downgrade() -> None:
    ts = _timestamp_default()

    # The pre-0002 schema keyed on vehicle_id as the (non-null) primary key, so any
    # detached rows (vehicle_id IS NULL) cannot survive the downgrade and are dropped.
    op.rename_table("dvsa_vehicles", "_dvsa_vehicles_old")
    op.create_table(
        "dvsa_vehicles",
        sa.Column(
            "vehicle_id",
            sa.Integer,
            sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
            primary_key=True,
            autoincrement=False,
        ),
        sa.Column("registration", sa.Text),
        sa.Column("make", sa.Text),
        sa.Column("model", sa.Text),
        sa.Column("first_used_date", sa.Text),
        sa.Column("fuel_type", sa.Text),
        sa.Column("primary_colour", sa.Text),
        sa.Column("registration_date", sa.Text),
        sa.Column("manufacture_date", sa.Text),
        sa.Column("manufacture_year", sa.Integer),
        sa.Column("engine_size", sa.Text),
        sa.Column("has_outstanding_recall", sa.Text),
        sa.Column("mot_test_due_date", sa.Text),
        sa.Column("raw_json", sa.Text, nullable=False),
        sa.Column("fetched_at", sa.Text, server_default=ts),
    )
    op.execute(
        f"INSERT INTO dvsa_vehicles ({', '.join(_CARRIED_COLUMNS)}) "
        f"SELECT {', '.join(_CARRIED_COLUMNS)} FROM _dvsa_vehicles_old "
        "WHERE vehicle_id IS NOT NULL"
    )
    op.drop_table("_dvsa_vehicles_old")
