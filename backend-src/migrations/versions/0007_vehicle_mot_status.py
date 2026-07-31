"""add vehicle_mot_status (DVLA VES current MOT status)

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-31

Adds ``vehicle_mot_status``: the DVLA VES "current MOT status" record (status + expiry),
scraped from the same gov.uk vehicle-enquiry page as ``vehicle_tax`` but stored as its
own record so it is distinct from the DVSA MOT *history* (``mot_tests``). The table is
created directly in the same shape ``vehicle_tax`` reached in migration 0006 — a
surrogate ``id`` primary key and a nullable ``vehicle_id`` foreign key with
``ON DELETE SET NULL`` plus ``UNIQUE`` (NULLs distinct on both Postgres and SQLite, so
any number of detached rows coexist while at most one *live* row exists per vehicle).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp_default() -> sa.TextClause:
    """A server default producing a UTC `YYYY-MM-DD HH:MM:SS` text timestamp."""
    if op.get_bind().dialect.name == "postgresql":
        return sa.text("to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')")
    return sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "vehicle_mot_status",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "vehicle_id",
            sa.Integer,
            sa.ForeignKey("vehicles.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
        ),
        sa.Column("registration", sa.Text),
        sa.Column("mot_status", sa.Text),
        sa.Column("mot_expiry_date", sa.Text),
        sa.Column("raw_json", sa.Text, nullable=False),
        sa.Column("fetched_at", sa.Text, server_default=_timestamp_default()),
    )


def downgrade() -> None:
    op.drop_table("vehicle_mot_status")
