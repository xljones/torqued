"""Tests for the database configuration layer (torqued/db.py)."""
import pytest
from torqued import db


def test_database_url_prefers_explicit_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "postgresql+psycopg://user:pass@localhost:5432/torqued"
    monkeypatch.setenv("DATABASE_URL", url)
    assert db.database_url() == url


def test_database_url_pins_psycopg_driver_on_provider_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Hosted providers (Neon, Heroku, …) hand out driverless URLs; pin psycopg v3 so
    # they can be pasted in verbatim, query string (e.g. ?sslmode=require) preserved.
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@ep-x.neon.tech/db?sslmode=require")
    assert db.database_url() == "postgresql+psycopg://u:p@ep-x.neon.tech/db?sslmode=require"
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@ep-x.neon.tech/db")
    assert db.database_url() == "postgresql+psycopg://u:p@ep-x.neon.tech/db"


def test_database_url_falls_back_to_sqlite_db_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_PATH", f"{tmp_path}/garage.db")
    assert db.database_url().startswith("sqlite:///")


def test_get_engine_builds_a_postgres_engine_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Engine construction is lazy: this exercises the PostgreSQL branch of
    # _create_engine without requiring a running database.
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/torqued_unit_test")
    engine = db.get_engine()
    assert engine.dialect.name == "postgresql"


def test_utcnow_text_is_iso_like() -> None:
    value = db.utcnow_text()
    assert len(value) == 19 and value[4] == "-" and value[10] == " "
