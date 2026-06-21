"""Alembic migration environment.

The database URL comes from the application configuration so that migrations
always target the same database the app does. Migrations are hand-written and
portable across SQLite (tests) and PostgreSQL (dev/prod); there is no ORM
metadata to autogenerate against.
"""
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the torqued package importable when Alembic is invoked from the CLI.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torqued.db import database_url  # noqa: E402

config = context.config
target_metadata = None


def _resolve_url() -> str:
    return config.get_main_option("sqlalchemy.url") or database_url()


def run_migrations_offline() -> None:
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _resolve_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
