"""retain vehicle tax records when their vehicle is deleted

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-30

Brings ``vehicle_tax`` to the same shape as ``dvsa_vehicles`` (migration 0002) so a
road-tax lookup is a first-class *record* that can outlive its vehicle and be relinked
later. Originally ``vehicle_tax.vehicle_id`` was both the primary key and a
``ON DELETE CASCADE`` foreign key, so at most one snapshot existed per vehicle and it
vanished with the vehicle. This migration restructures the table:

* a surrogate autoincrement ``id`` becomes the primary key;
* ``vehicle_id`` becomes a nullable foreign key with ``ON DELETE SET NULL`` plus a
  ``UNIQUE`` constraint (NULLs are distinct on both Postgres and SQLite, so any number
  of detached rows coexist while at most one *live* row exists per vehicle).

A deleted vehicle's tax row then survives with ``vehicle_id = NULL`` (a "detached"
record), and refreshes keep the previous lookup as history rather than deleting it.
The table is rebuilt by hand (rename → create → copy → drop) exactly like 0002:
SQLite (the test backend) cannot drop/alter constraints in place, and a plain rebuild
is identical on both backends.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Columns carried across the rebuild, in declaration order (everything except the
# primary key, which is reassigned by the destination table).
_CARRIED_COLUMNS = (
    "vehicle_id",
    "registration",
    "tax_status",
    "tax_due_date",
    "raw_json",
    "fetched_at",
)


def _timestamp_default() -> sa.TextClause:
    """A server default producing a UTC `YYYY-MM-DD HH:MM:SS` text timestamp."""
    if op.get_bind().dialect.name == "postgresql":
        return sa.text("to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')")
    return sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    ts = _timestamp_default()

    op.rename_table("vehicle_tax", "_vehicle_tax_old")
    op.create_table(
        "vehicle_tax",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "vehicle_id",
            sa.Integer,
            sa.ForeignKey("vehicles.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
        ),
        sa.Column("registration", sa.Text),
        sa.Column("tax_status", sa.Text),
        sa.Column("tax_due_date", sa.Text),
        sa.Column("raw_json", sa.Text, nullable=False),
        sa.Column("fetched_at", sa.Text, server_default=ts),
    )
    cols = ", ".join(_CARRIED_COLUMNS)
    op.execute(f"INSERT INTO vehicle_tax ({cols}) SELECT {cols} FROM _vehicle_tax_old")
    op.drop_table("_vehicle_tax_old")


def downgrade() -> None:
    ts = _timestamp_default()

    # The pre-0006 schema keyed on vehicle_id as the (non-null) primary key, so any
    # detached rows (vehicle_id IS NULL) cannot survive the downgrade and are dropped.
    op.rename_table("vehicle_tax", "_vehicle_tax_old")
    op.create_table(
        "vehicle_tax",
        sa.Column(
            "vehicle_id",
            sa.Integer,
            sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
            primary_key=True,
            autoincrement=False,
        ),
        sa.Column("registration", sa.Text),
        sa.Column("tax_status", sa.Text),
        sa.Column("tax_due_date", sa.Text),
        sa.Column("raw_json", sa.Text, nullable=False),
        sa.Column("fetched_at", sa.Text, server_default=ts),
    )
    op.execute(
        f"INSERT INTO vehicle_tax ({', '.join(_CARRIED_COLUMNS)}) "
        f"SELECT {', '.join(_CARRIED_COLUMNS)} FROM _vehicle_tax_old "
        "WHERE vehicle_id IS NOT NULL"
    )
    op.drop_table("_vehicle_tax_old")
