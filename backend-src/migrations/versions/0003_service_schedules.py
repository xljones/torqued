"""service schedules

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-24

Per-vehicle recurring service schedules. A vehicle can have a 'minor' schedule, a
'major' schedule, and any number of user-named 'custom' schedules, each with an
interval expressed as every N months and/or every N km. Service logs gain a nullable
``service_schedule_id`` recording which schedule a given service fulfilled — the anchor
from which the next due date/mileage is projected.

Portability: the new column is added with a plain ``ADD COLUMN`` carrying **no** foreign
key. Alembic implements an inline-FK ``add_column`` as a separate ``ADD CONSTRAINT``,
which SQLite (the test backend) cannot do in place — and the only alternative, a full
``service_logs`` rebuild, would be unsafe on a populated database anyway, since dropping
the table cascades to the photos and fault-code rows that reference it. So the FK is
omitted and its ``ON DELETE SET NULL`` behaviour is enforced in
``ServiceScheduleRepository.delete`` instead (null the fulfilling logs' link before
removing the schedule). ``service_log_history`` likewise carries a plain column, matching
the denormalised audit-snapshot convention of the other ``*_history`` tables.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp_default() -> sa.TextClause:
    """A server default producing a UTC `YYYY-MM-DD HH:MM:SS` text timestamp."""
    if op.get_bind().dialect.name == "postgresql":
        return sa.text("to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')")
    return sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    ts = _timestamp_default()

    op.create_table(
        "service_schedules",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "vehicle_id",
            sa.Integer,
            sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("name", sa.Text),
        sa.Column("interval_months", sa.Integer),
        sa.Column("interval_km", sa.Float),
        sa.Column("enabled", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.Text, server_default=ts),
        sa.Column("updated_at", sa.Text, server_default=ts),
    )
    op.create_index("idx_service_schedules_vehicle", "service_schedules", ["vehicle_id"])

    # Link a service log to the schedule it fulfilled. No live FK (see module docstring);
    # the repository nulls this column when its schedule is deleted.
    op.add_column(
        "service_logs",
        sa.Column("service_schedule_id", sa.Integer, nullable=True),
    )
    # History is a denormalised audit snapshot (like the other *_history tables): a plain
    # nullable column, no foreign key.
    op.add_column(
        "service_log_history",
        sa.Column("service_schedule_id", sa.Integer, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("service_log_history", "service_schedule_id")
    op.drop_column("service_logs", "service_schedule_id")
    op.drop_index("idx_service_schedules_vehicle", table_name="service_schedules")
    op.drop_table("service_schedules")
