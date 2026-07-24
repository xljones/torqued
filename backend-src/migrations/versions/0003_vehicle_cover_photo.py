"""add user-selectable cover photo to vehicles

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-24

The cover photo shown for a vehicle (the list-card thumbnail, and now a glyph in the
photo grid) was previously derived entirely at query time. This adds a nullable
``vehicles.cover_photo_id`` column so a user can pin a specific photo as the cover;
while it is NULL the app falls back to the most recently uploaded photo.

It is a plain nullable integer, not a database foreign key. Adding an FK constraint to
an existing table is not portable to SQLite (the test backend), which cannot alter
constraints in place and would need a full rebuild of the heavily-referenced
``vehicles`` table (see revision 0002). Referential integrity — clearing the column
when the referenced photo is deleted — is enforced in the repository layer instead,
consistent with the ORM models deliberately omitting foreign keys.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("vehicles", sa.Column("cover_photo_id", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("vehicles", "cover_photo_id")
