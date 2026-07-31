"""add cover-crop framing to photos

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-31

The vehicle-card cover image is a fixed-ratio (16:9) box rendered with
``object-fit: cover``, which always crops a photo centered — there was no way to choose
*which part* of a photo shows. This adds a per-photo focal point (``cover_focal_x``/
``cover_focal_y``, a fraction 0..1 of the image) plus a ``cover_zoom`` multiplier on top of
the natural cover-fit scale, set via the photo lightbox's "Edit cover" pan/zoom tool.

All three columns are nullable with no DB default: NULL reproduces today's plain centered
crop exactly (treated as 0.5/0.5/1.0 in application code). Framing is stored per-photo
rather than per-vehicle so it survives re-selecting a previously-used cover photo, and
naturally disappears when the photo row is deleted — no extra cleanup needed. As with
``vehicles.cover_photo_id`` (revision 0003), valid ranges are enforced in the route layer,
not via a DB ``CHECK`` constraint, keeping the migration portable across SQLite and Postgres.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("photos", sa.Column("cover_focal_x", sa.Float, nullable=True))
    op.add_column("photos", sa.Column("cover_focal_y", sa.Float, nullable=True))
    op.add_column("photos", sa.Column("cover_zoom", sa.Float, nullable=True))


def downgrade() -> None:
    op.drop_column("photos", "cover_zoom")
    op.drop_column("photos", "cover_focal_y")
    op.drop_column("photos", "cover_focal_x")
