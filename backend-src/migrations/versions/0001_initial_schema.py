"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-17

The complete Torqued schema. Written to be portable across SQLite (tests) and
PostgreSQL (dev/prod): dates and timestamps are stored as TEXT (ISO strings) so
the values round-trip identically on both backends, and 0/1 flags stay INTEGER.
The only dialect-specific touch is the CURRENT_TIMESTAMP default, which is
rendered as a UTC `YYYY-MM-DD HH:MM:SS` text literal on each backend.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
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
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.Text, nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("is_admin", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("expires_at", sa.Text),
        sa.Column("created_at", sa.Text, server_default=ts),
    )

    op.create_table(
        "garages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", sa.Text, server_default=ts),
    )

    op.create_table(
        "garage_members",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "garage_id",
            sa.Integer,
            sa.ForeignKey("garages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text, nullable=False, server_default=sa.text("'member'")),
        sa.Column("created_at", sa.Text, server_default=ts),
        sa.UniqueConstraint("garage_id", "user_id", name="uq_garage_members_garage_user"),
    )

    op.create_table(
        "vehicles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "garage_id",
            sa.Integer,
            sa.ForeignKey("garages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False, server_default=sa.text("'car'")),
        sa.Column("make", sa.Text),
        sa.Column("model", sa.Text),
        sa.Column("year", sa.Integer),
        sa.Column("registration", sa.Text),
        sa.Column("vin", sa.Text),
        sa.Column("colour", sa.Text),
        sa.Column("fuel_type", sa.Text),
        sa.Column("engine_size", sa.Text),
        sa.Column("first_used_date", sa.Text),
        sa.Column("registration_date", sa.Text),
        sa.Column("odometer_unit", sa.Text, nullable=False, server_default=sa.text("'mi'")),
        sa.Column("purchase_date", sa.Text),
        sa.Column("tyre_size_front", sa.Text),
        sa.Column("tyre_size_rear", sa.Text),
        sa.Column("tyre_pressure_front_psi", sa.Float),
        sa.Column("tyre_pressure_rear_psi", sa.Float),
        sa.Column("notes", sa.Text),
        sa.Column("archived", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.Text, server_default=ts),
        sa.Column("updated_at", sa.Text, server_default=ts),
    )

    op.create_table(
        "vehicle_specs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "vehicle_id",
            sa.Integer,
            sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.Text, server_default=ts),
    )

    op.create_table(
        "service_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "vehicle_id",
            sa.Integer,
            sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("category", sa.Text),
        sa.Column("description", sa.Text),
        sa.Column("performed_by", sa.Text),
        sa.Column("cost", sa.Float),
        sa.Column("odometer_km", sa.Float),
        sa.Column("odometer_unit", sa.Text),
        sa.Column("next_due_date", sa.Text),
        sa.Column("next_due_km", sa.Float),
        sa.Column("created_at", sa.Text, server_default=ts),
        sa.Column("updated_at", sa.Text, server_default=ts),
    )

    op.create_table(
        "odometer_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "vehicle_id",
            sa.Integer,
            sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Text, nullable=False),
        sa.Column("odometer_km", sa.Float, nullable=False),
        sa.Column("unit", sa.Text, nullable=False, server_default=sa.text("'mi'")),
        sa.Column("note", sa.Text),
        sa.Column("source", sa.Text, nullable=False, server_default=sa.text("'manual'")),
        sa.Column("mot_test_number", sa.Text),
        sa.Column("created_at", sa.Text, server_default=ts),
    )

    op.create_table(
        "photos",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "vehicle_id",
            sa.Integer,
            sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "service_log_id",
            sa.Integer,
            sa.ForeignKey("service_logs.id", ondelete="CASCADE"),
        ),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("original_name", sa.Text),
        sa.Column("caption", sa.Text),
        sa.Column("uploaded_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.Text, server_default=ts),
    )

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

    op.create_table(
        "mot_tests",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "vehicle_id",
            sa.Integer,
            sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("completed_date", sa.Text, nullable=False),
        sa.Column("test_result", sa.Text),
        sa.Column("expiry_date", sa.Text),
        sa.Column("odometer_value", sa.Integer),
        sa.Column("odometer_unit", sa.Text),
        sa.Column("odometer_result_type", sa.Text),
        sa.Column("mot_test_number", sa.Text),
        sa.Column("data_source", sa.Text),
        sa.Column("location", sa.Text),
        sa.Column("defects_json", sa.Text, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("raw_json", sa.Text, nullable=False),
    )

    op.create_table(
        "service_log_fault_codes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "service_log_id",
            sa.Integer,
            sa.ForeignKey("service_logs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.Text, nullable=False),
    )

    op.create_table(
        "vehicle_history",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "vehicle_id",
            sa.Integer,
            sa.ForeignKey("vehicles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("changed_at", sa.Text, server_default=ts),
        sa.Column("changed_by", sa.Integer),
        sa.Column("name", sa.Text),
        sa.Column("kind", sa.Text),
        sa.Column("make", sa.Text),
        sa.Column("model", sa.Text),
        sa.Column("year", sa.Integer),
        sa.Column("registration", sa.Text),
        sa.Column("vin", sa.Text),
        sa.Column("colour", sa.Text),
        sa.Column("fuel_type", sa.Text),
        sa.Column("engine_size", sa.Text),
        sa.Column("first_used_date", sa.Text),
        sa.Column("registration_date", sa.Text),
        sa.Column("odometer_unit", sa.Text),
        sa.Column("purchase_date", sa.Text),
        sa.Column("tyre_size_front", sa.Text),
        sa.Column("tyre_size_rear", sa.Text),
        sa.Column("tyre_pressure_front_psi", sa.Float),
        sa.Column("tyre_pressure_rear_psi", sa.Float),
        sa.Column("notes", sa.Text),
        sa.Column("archived", sa.Integer),
    )

    op.create_table(
        "service_log_history",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "service_log_id",
            sa.Integer,
            sa.ForeignKey("service_logs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("changed_at", sa.Text, server_default=ts),
        sa.Column("changed_by", sa.Integer),
        sa.Column("vehicle_id", sa.Integer),
        sa.Column("date", sa.Text),
        sa.Column("title", sa.Text),
        sa.Column("category", sa.Text),
        sa.Column("description", sa.Text),
        sa.Column("performed_by", sa.Text),
        sa.Column("cost", sa.Float),
        sa.Column("odometer_km", sa.Float),
        sa.Column("odometer_unit", sa.Text),
        sa.Column("next_due_date", sa.Text),
        sa.Column("next_due_km", sa.Float),
    )

    op.create_index("idx_vehicles_garage", "vehicles", ["garage_id"])
    op.create_index("idx_garage_members_user", "garage_members", ["user_id"])
    op.create_index(
        "idx_service_logs_vehicle", "service_logs", ["vehicle_id", sa.text("date DESC")]
    )
    op.create_index(
        "idx_odometer_logs_vehicle", "odometer_logs", ["vehicle_id", sa.text("date DESC")]
    )
    op.create_index("idx_photos_vehicle", "photos", ["vehicle_id"])
    op.create_index("idx_photos_service_log", "photos", ["service_log_id"])
    op.create_index(
        "idx_mot_tests_vehicle", "mot_tests", ["vehicle_id", sa.text("completed_date DESC")]
    )
    op.create_index("idx_slfc_service", "service_log_fault_codes", ["service_log_id"])


def downgrade() -> None:
    for table in (
        "service_log_history",
        "vehicle_history",
        "service_log_fault_codes",
        "mot_tests",
        "dvsa_vehicles",
        "photos",
        "odometer_logs",
        "service_logs",
        "vehicle_specs",
        "vehicles",
        "garage_members",
        "garages",
        "users",
    ):
        op.drop_table(table)
