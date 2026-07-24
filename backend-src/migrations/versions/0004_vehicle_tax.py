"""vehicle tax / SORN status

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-24

One stored road-tax snapshot per vehicle (tax status, SORN, and the tax due date),
plus the raw scraped payload. Kept lean and portable across SQLite (tests) and
PostgreSQL (dev/prod): dates are TEXT (ISO strings) and the only dialect-specific
touch is the CURRENT_TIMESTAMP default, matching revision 0001.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp_default() -> sa.TextClause:
    """A server default producing a UTC `YYYY-MM-DD HH:MM:SS` text timestamp."""
    if op.get_bind().dialect.name == "postgresql":
        return sa.text("to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')")
    return sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
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
        sa.Column("fetched_at", sa.Text, server_default=_timestamp_default()),
    )


def downgrade() -> None:
    op.drop_table("vehicle_tax")
