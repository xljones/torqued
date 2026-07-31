"""rename vehicle_tax -> vehicle_ves and extend it to the full VES snapshot

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-31

One DVLA VES lookup returns tax status, MOT status, and the whole vehicle profile in a
single fetch, so it belongs in one record rather than split across tables. This renames
the existing ``vehicle_tax`` table to ``vehicle_ves`` (keeping all stored tax history and
its detached-record shape from migration 0006) and adds the columns promoted for queries:
``mot_status``, ``mot_expiry_date`` (MOT reminders / list pill) and ``make``/``colour``
(records display). The remaining profile fields (cylinder capacity, CO₂, fuel, Euro
status, wheelplan, V5C date, …) live verbatim in ``raw_json``.

Adding nullable columns and renaming a table are portable across Postgres and SQLite, so
no table rebuild is needed on upgrade. The downgrade rebuilds the original ``vehicle_tax``
(dropping the new columns and any MOT-only data) the same way 0006 does.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_COLUMNS = ("mot_status", "mot_expiry_date", "make", "colour")
# Columns carried when rebuilding vehicle_tax on downgrade (everything except the PK).
_TAX_COLUMNS = ("vehicle_id", "registration", "tax_status", "tax_due_date", "raw_json", "fetched_at")


def _timestamp_default() -> sa.TextClause:
    """A server default producing a UTC `YYYY-MM-DD HH:MM:SS` text timestamp."""
    if op.get_bind().dialect.name == "postgresql":
        return sa.text("to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')")
    return sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.rename_table("vehicle_tax", "vehicle_ves")
    for name in _NEW_COLUMNS:
        op.add_column("vehicle_ves", sa.Column(name, sa.Text))


def downgrade() -> None:
    ts = _timestamp_default()
    op.rename_table("vehicle_ves", "_vehicle_ves_old")
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
    cols = ", ".join(_TAX_COLUMNS)
    op.execute(f"INSERT INTO vehicle_tax ({cols}) SELECT {cols} FROM _vehicle_ves_old")
    op.drop_table("_vehicle_ves_old")
