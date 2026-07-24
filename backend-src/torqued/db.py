"""Database access layer.

The application is database-agnostic: it uses SQLite by default (development,
tests, and production) and can talk to PostgreSQL instead, through a single
SQLAlchemy engine. The backing store is chosen entirely by configuration:

* ``DATABASE_URL`` — a full SQLAlchemy URL (e.g.
  ``postgresql+psycopg://user:pass@host:5432/torqued``). Set this to use PostgreSQL.
* ``DB_PATH`` — a path to a SQLite file; resolved to a ``sqlite:///`` URL.
* neither set — falls back to an on-disk SQLite file under ``data/``.

Repositories never import a driver; they receive a :class:`~sqlalchemy.orm.Session`
from :func:`get_db` — one per request, inside a transaction — and use the ORM directly.
:func:`execute_sql` remains for the occasional ad-hoc raw statement (CLI maintenance,
tests), translating the ordinary ``"… WHERE id = ?"`` qmark convention to named
parameters.
"""
import os
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

# IntegrityError is re-exported so routes can catch a duplicate-key violation
# without importing a driver (or SQLAlchemy) directly — keeping them oblivious
# to which backend is in use.
__all__ = [
    "IntegrityError",
    "database_url",
    "execute_sql",
    "get_db",
    "run_migrations",
    "utcnow_text",
]

_DEFAULT_DB_PATH = str(Path(__file__).parent.parent.parent / "data" / "garage.db")
_MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"

# Engines are cached per-URL: the app reuses one engine, while each test's
# temporary SQLite file gets its own (keeping test databases isolated).
_engines: dict[str, Engine] = {}


def _with_psycopg_driver(url: str) -> str:
    """Pin the psycopg v3 driver on a bare PostgreSQL URL.

    Lets a hosted-provider connection string (a managed Postgres, Heroku,
    Railway, …) be used verbatim: those come as ``postgres://`` or
    ``postgresql://``, for which SQLAlchemy would otherwise pick the (uninstalled)
    psycopg2 driver.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def database_url() -> str:
    """Resolve the SQLAlchemy URL for the active database (see module docstring)."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return _with_psycopg_driver(url)
    db_path = os.environ.get("DB_PATH", _DEFAULT_DB_PATH)
    return URL.create("sqlite", database=db_path).render_as_string(hide_password=False)


def _create_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        engine = create_engine(url, poolclass=NullPool)

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_conn: Any, _: Any) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    # prepare_threshold=None disables psycopg's server-side prepared statements,
    # which don't survive a transaction-pooling proxy such as PgBouncer
    # (otherwise: "prepared statement … does not exist").
    return create_engine(url, pool_pre_ping=True, connect_args={"prepare_threshold": None})


def get_engine() -> Engine:
    """Return the cached engine for the active database URL, creating it once."""
    url = database_url()
    if url not in _engines:
        _engines[url] = _create_engine(url)
    return _engines[url]


def _to_named(sql: str, params: Sequence[Any]) -> tuple[str, dict[str, Any]]:
    """Translate qmark (``?``) placeholders to SQLAlchemy named (``:p0``) ones.

    Question marks inside single-quoted string literals are left untouched.
    """
    out: list[str] = []
    bound: dict[str, Any] = {}
    in_literal = False
    index = 0
    for char in sql:
        if char == "'":
            in_literal = not in_literal
            out.append(char)
        elif char == "?" and not in_literal:
            key = f"p{index}"
            out.append(f":{key}")
            bound[key] = params[index]
            index += 1
        else:
            out.append(char)
    return "".join(out), bound


def execute_sql(session: Session, sql: str, params: Sequence[Any] = ()) -> Any:
    """Run an ad-hoc ``?``-placeholder statement on *session*.

    Repositories use the ORM directly; this remains for the occasional raw statement in
    CLI maintenance and tests, translating the qmark convention to named parameters.
    """
    statement, bound = _to_named(sql, params)
    return session.execute(text(statement), bound)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Yield a session inside a transaction (committed on success, else rolled back)."""
    with Session(get_engine()) as session, session.begin():
        yield session


def utcnow_text() -> str:
    """Current UTC time formatted to match the schema's ``CURRENT_TIMESTAMP`` default."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def run_migrations() -> None:
    """Bring the database up to the latest Alembic revision."""
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", database_url())
    command.upgrade(config, "head")
