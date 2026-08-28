"""add per-garage maintenance reminder windows

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-27

How far ahead a reminder counts as "due soon" was fixed in module constants — 30 days /
500 km for service and schedule reminders, 60 days for the MOT, 30 days for road tax. 500 km
is barely a fortnight's driving for a daily, and far too eager for a project bike, so the
windows are now set per garage.

Five nullable columns with no DB default: NULL means "use the application default" (see
``torqued/reminders.py``), keeping defaults in Python where the rest of them live and the
migration portable across SQLite and Postgres. Nothing is back-filled — existing garages
pick up the new default distance (2,000 mi, up from 500 km; the 30-day half is unchanged).

The service distance is stored canonically in km alongside the unit the user typed, the
same pair as ``vehicles.odometer_km``/``odometer_unit``, so a garage that entered "2,000 mi"
reads back 2,000 mi rather than 3,219 km. As with ``photos.cover_zoom`` (revision 0008),
ranges are validated in the route layer, not via a DB ``CHECK`` constraint.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("garages", sa.Column("reminder_service_days", sa.Integer, nullable=True))
    op.add_column("garages", sa.Column("reminder_service_km", sa.Float, nullable=True))
    op.add_column("garages", sa.Column("reminder_service_unit", sa.Text, nullable=True))
    op.add_column("garages", sa.Column("reminder_mot_days", sa.Integer, nullable=True))
    op.add_column("garages", sa.Column("reminder_tax_days", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("garages", "reminder_tax_days")
    op.drop_column("garages", "reminder_mot_days")
    op.drop_column("garages", "reminder_service_unit")
    op.drop_column("garages", "reminder_service_km")
    op.drop_column("garages", "reminder_service_days")
