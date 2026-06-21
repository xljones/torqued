"""Tests for the dev-only login database switcher.

Two throwaway SQLite databases stand in for "local" and "production": each gets a
distinct user, so we can prove a login lands on the database the request selected.
"""
import os
import tempfile
from collections.abc import Generator

import pytest
from flask.testing import FlaskClient


def _seed_user(db_path: str, username: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Create a user in the SQLite database at db_path (via default DB_PATH resolution)."""
    from torqued.db import get_db, run_migrations

    monkeypatch.setenv("DB_PATH", db_path)
    run_migrations()
    with get_db() as db:
        from torqued.repositories.user_repository import UserRepository

        UserRepository(db).create(username, "pw")


def _make_client(
    monkeypatch: pytest.MonkeyPatch, *, switcher: bool
) -> Generator[FlaskClient, None, None]:
    local_fd, local = tempfile.mkstemp(suffix=".db")
    os.close(local_fd)
    prod_fd, prod = tempfile.mkstemp(suffix=".db")
    os.close(prod_fd)
    monkeypatch.setenv("UPLOAD_DIR", tempfile.mkdtemp())
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PROD_DATABASE_URL", f"sqlite:///{prod}")
    # FLASK_DEBUG is on in *both* cases on purpose: the switcher must depend solely on
    # the explicit ENABLE_DB_SWITCHER opt-in, never on dev mode.
    monkeypatch.setenv("FLASK_DEBUG", "1")
    if switcher:
        monkeypatch.setenv("ENABLE_DB_SWITCHER", "1")
    else:
        monkeypatch.delenv("ENABLE_DB_SWITCHER", raising=False)
    monkeypatch.setenv("SECRET_KEY", "test-secret")

    _seed_user(prod, "produser", monkeypatch)
    _seed_user(local, "localuser", monkeypatch)
    monkeypatch.setenv("DB_PATH", local)  # local is the default backend

    from torqued import create_app

    app = create_app()
    app.config["TESTING"] = True
    yield app.test_client()
    os.unlink(local)
    os.unlink(prod)


@pytest.fixture
def switcher_client(monkeypatch: pytest.MonkeyPatch) -> Generator[FlaskClient, None, None]:
    yield from _make_client(monkeypatch, switcher=True)


@pytest.fixture
def no_switcher_client(monkeypatch: pytest.MonkeyPatch) -> Generator[FlaskClient, None, None]:
    yield from _make_client(monkeypatch, switcher=False)


def _login(client: FlaskClient, username: str, database: str | None = None) -> object:
    body: dict[str, str] = {"username": username, "password": "pw"}
    if database is not None:
        body["database"] = database
    return client.post("/api/auth/login", json=body)


def test_config_advertises_switcher_when_opted_in(switcher_client: FlaskClient) -> None:
    r = switcher_client.get("/api/config")
    assert r.status_code == 200
    assert r.json["db_switcher"] is True


def test_login_to_production_uses_the_production_database(switcher_client: FlaskClient) -> None:
    r = _login(switcher_client, "produser", "production")  # exists only in the prod DB
    assert r.status_code == 200
    assert r.json["database"] == "production"
    assert switcher_client.get("/api/auth/me").json["database"] == "production"


def test_login_to_production_cannot_see_local_only_users(switcher_client: FlaskClient) -> None:
    assert _login(switcher_client, "localuser", "production").status_code == 401


def test_login_to_local_uses_the_local_database(switcher_client: FlaskClient) -> None:
    r = _login(switcher_client, "localuser", "local")
    assert r.status_code == 200
    assert r.json["database"] == "local"
    assert _login(switcher_client, "produser", "local").status_code == 401


def test_login_defaults_to_local_when_no_database_given(switcher_client: FlaskClient) -> None:
    r = _login(switcher_client, "localuser")
    assert r.status_code == 200
    assert r.json["database"] == "local"


def test_logout_resets_the_db_target(switcher_client: FlaskClient) -> None:
    assert _login(switcher_client, "produser", "production").status_code == 200
    switcher_client.post("/api/auth/logout")
    # The production binding is cleared, so a subsequent local login lands on local.
    assert _login(switcher_client, "localuser", "local").json["database"] == "local"


def test_switcher_is_inert_without_opt_in(no_switcher_client: FlaskClient) -> None:
    # FLASK_DEBUG=1 and PROD_DATABASE_URL set, but ENABLE_DB_SWITCHER is not: the
    # switcher stays off, proving it no longer keys off dev mode.
    assert no_switcher_client.get("/api/config").json["db_switcher"] is False
    # A "production" hint is ignored: the request stays on the default (local) DB.
    assert _login(no_switcher_client, "produser", "production").status_code == 401
    assert _login(no_switcher_client, "localuser", "production").status_code == 200


def test_switcher_unavailable_without_prod_url(client: FlaskClient) -> None:
    # Default test client: no opt-in and no PROD_DATABASE_URL configured.
    assert client.get("/api/config").json["db_switcher"] is False
