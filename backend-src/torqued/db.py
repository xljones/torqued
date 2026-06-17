"""Database access layer.

The application is database-agnostic: it talks to PostgreSQL in development and
production and to SQLite during tests, through a single SQLAlchemy engine. The
backing store is chosen entirely by configuration:

* ``DATABASE_URL`` — a full SQLAlchemy URL (e.g.
  ``postgresql+psycopg://user:pass@host:5432/torqued``). Used in dev/prod.
* ``DB_PATH`` — a path to a SQLite file. Convenient for tests and quick local
  runs; resolved to a ``sqlite:///`` URL.
* neither set — falls back to an on-disk SQLite file under ``data/``.

Repositories never import a driver or this module's internals; they receive a
:class:`Connection` from :func:`get_db` and execute SQL through it using the
ordinary ``"… WHERE id = ?"`` + parameter-tuple convention. The wrapper takes
care of the dialect (placeholder style, row mapping, transactions).
"""
import os
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import CursorResult, RowMapping, create_engine, event, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.engine import Connection as SAConnection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

# IntegrityError is re-exported so routes can catch a duplicate-key violation
# without importing a driver (or SQLAlchemy) directly — keeping them oblivious
# to which backend is in use.
__all__ = [
    "Connection",
    "IntegrityError",
    "database_url",
    "get_db",
    "run_migrations",
    "utcnow_text",
]

_DEFAULT_DB_PATH = str(Path(__file__).parent.parent.parent / "data" / "garage.db")
_MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"

# Engines are cached per-URL: prod reuses one pooled engine, while each test's
# temporary SQLite file gets its own (keeping test databases isolated).
_engines: dict[str, Engine] = {}


def database_url() -> str:
    """Resolve the SQLAlchemy URL for the active database (see module docstring)."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
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
    return create_engine(url, pool_pre_ping=True)


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


class Result:
    """The rows of one executed statement, exposed as plain dict-like mappings."""

    def __init__(self, cursor: CursorResult[Any]) -> None:
        self._rowcount = cursor.rowcount
        self._rows: list[RowMapping] = list(cursor.mappings()) if cursor.returns_rows else []

    def fetchone(self) -> RowMapping | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[RowMapping]:
        return self._rows

    @property
    def rowcount(self) -> int:
        return self._rowcount


class Connection:
    """Dialect-agnostic wrapper over a SQLAlchemy connection.

    Accepts the repositories' ``execute("… ? …", (args,))`` convention and returns
    :class:`Result` objects whose rows behave like dictionaries.
    """

    def __init__(self, connection: SAConnection) -> None:
        self._connection = connection

    def execute(self, sql: str, params: Sequence[Any] = ()) -> Result:
        statement, bound = _to_named(sql, params)
        return Result(self._connection.execute(text(statement), bound))


@contextmanager
def get_db() -> Generator[Connection, None, None]:
    """Yield a connection inside a transaction (committed on success, else rolled back)."""
    with get_engine().begin() as connection:
        yield Connection(connection)


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
