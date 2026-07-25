"""service schedules

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-24

Per-vehicle recurring service schedules. A vehicle can have a 'minor' schedule, a
'major' schedule, and any number of user-named 'custom' schedules, each with an
interval expressed as every N months and/or every N km.

A single service can fulfil more than one schedule (e.g. a major service that also
covers the minor one), so the link is many-to-many: ``service_log_service_schedules``
joins a service log to each schedule it fulfilled. The newest fulfilling log is the
anchor from which a schedule's next due date/mileage is projected. Both foreign keys
cascade on delete — removing a schedule or a service log just drops its join rows —
which is safe here because the join table is created fresh (a ``CREATE TABLE`` with
inline FKs is fully supported on SQLite, unlike an ``ALTER … ADD COLUMN … REFERENCES``).

The schedule linkage is intentionally not snapshotted into ``service_log_history``:
it is auxiliary to the log's own fields and the live links are always queryable.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
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

    # Many-to-many link: which schedule(s) a given service fulfilled. Both sides cascade
    # on delete; the unique pair keeps a service from linking the same schedule twice.
    op.create_table(
        "service_log_service_schedules",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "service_log_id",
            sa.Integer,
            sa.ForeignKey("service_logs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "service_schedule_id",
            sa.Integer,
            sa.ForeignKey("service_schedules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "service_log_id", "service_schedule_id", name="uq_service_log_schedule"
        ),
    )
    op.create_index(
        "idx_slss_schedule", "service_log_service_schedules", ["service_schedule_id"]
    )
    op.create_index("idx_slss_log", "service_log_service_schedules", ["service_log_id"])


def downgrade() -> None:
    op.drop_index("idx_slss_log", table_name="service_log_service_schedules")
    op.drop_index("idx_slss_schedule", table_name="service_log_service_schedules")
    op.drop_table("service_log_service_schedules")
    op.drop_index("idx_service_schedules_vehicle", table_name="service_schedules")
    op.drop_table("service_schedules")
