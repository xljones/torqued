"""Tests for torqued/__init__.py: middleware, frontend serving, app factory."""
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import Flask
from flask.testing import FlaskClient

from torqued.db import execute_sql, get_db
from torqued.repositories.user_repository import UserRepository


# ── domain model ─────────────────────────────────────────────────────────────

def test_domain_models_importable() -> None:
    from torqued.domain.garage import Garage
    from torqued.domain.odometer_log import OdometerLog
    from torqued.domain.photo import Photo
    from torqued.domain.service_log import ServiceLog
    from torqued.domain.vehicle import Vehicle

    assert Garage(id=1, name="Home").name == "Home"
    assert Vehicle(id=1, name="Daily").name == "Daily"
    assert ServiceLog(id=1, vehicle_id=1, date="2025-01-01", title="Oil").title == "Oil"
    assert OdometerLog(id=1, vehicle_id=1, date="2025-01-01", odometer_km=100.0).odometer_km == 100.0
    assert Photo(id=1, vehicle_id=1, filename="x.jpg").filename == "x.jpg"


def test_user_is_active_no_expiry() -> None:
    from torqued.domain.user import User
    assert User(id=1, username="u").is_active is True


def test_user_is_active_future_expiry() -> None:
    from torqued.domain.user import User
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert User(id=1, username="u", expires_at=future).is_active is True


def test_user_is_active_past_expiry() -> None:
    from torqued.domain.user import User
    assert User(id=1, username="u", expires_at="2000-01-01T00:00:00+00:00").is_active is False


def test_user_is_active_invalid_format() -> None:
    from torqued.domain.user import User
    assert User(id=1, username="u", expires_at="not-a-date").is_active is True


# ── app factory ───────────────────────────────────────────────────────────────

def test_create_app_requires_secret_key_in_production(tmp_path: Path) -> None:
    db_fd, db_path = tempfile.mkstemp(suffix=".db", dir=tmp_path)
    os.close(db_fd)
    env = {k: v for k, v in os.environ.items() if k != "SECRET_KEY"}
    env["FLASK_DEBUG"] = "0"
    env["DB_PATH"] = db_path
    with patch.dict(os.environ, env, clear=True):
        from torqued import create_app
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            create_app()


def test_create_app_skips_startup_migration_on_pythonanywhere(monkeypatch) -> None:
    """On PythonAnywhere the per-worker startup migration is skipped — migrations are
    applied explicitly (single process) by `make migrate`, so concurrent web workers
    can't race to build the schema ('table users already exists' on first boot)."""
    called = []
    monkeypatch.setattr("torqued.db.run_migrations", lambda: called.append(1))
    monkeypatch.setenv("PYTHONANYWHERE_SITE", "xljones.pythonanywhere.com")
    from torqued import create_app
    create_app()
    assert called == []


def test_create_app_runs_startup_migration_off_pythonanywhere(monkeypatch) -> None:
    """Off PythonAnywhere (local / Docker) the app still migrates on startup, so it's
    ready on first boot with no extra step."""
    called = []
    monkeypatch.setattr("torqued.db.run_migrations", lambda: called.append(1))
    monkeypatch.delenv("PYTHONANYWHERE_SITE", raising=False)
    from torqued import create_app
    create_app()
    assert called == [1]


# ── enforce_auth middleware ───────────────────────────────────────────────────

def test_enforce_auth_expired_session(client: FlaskClient) -> None:
    with get_db() as db:
        user = UserRepository(db).create("expireme", "pass")
    client.post("/api/auth/login", json={"username": "expireme", "password": "pass"})
    with get_db() as db:
        execute_sql(
            db,
            "UPDATE users SET expires_at=? WHERE id=?",
            ("2000-01-01T00:00:00+00:00", user["id"]),
        )
    r = client.get("/api/vehicles")
    assert r.status_code == 401
    assert "expired" in r.json["error"].lower()


def test_enforce_auth_invalid_expires_at_ignored(client: FlaskClient) -> None:
    with get_db() as db:
        user = UserRepository(db).create("badexpiry", "pass")
    client.post("/api/auth/login", json={"username": "badexpiry", "password": "pass"})
    with get_db() as db:
        execute_sql(
            db,
            "UPDATE users SET expires_at=? WHERE id=?",
            ("not-a-valid-date", user["id"]),
        )
    r = client.get("/api/vehicles")
    assert r.status_code == 200


def test_readonly_member_blocked_from_writes(readonly_client: FlaskClient) -> None:
    garage_id = readonly_client.get("/api/garages").json[0]["id"]
    r = readonly_client.post("/api/vehicles", json={"name": "Bike", "garage_id": garage_id})
    assert r.status_code == 403
    assert "read-only" in r.json["error"].lower()


def test_readonly_member_can_change_password(readonly_client: FlaskClient) -> None:
    r = readonly_client.put("/api/auth/password", json={
        "current_password": "testpass", "new_password": "newpass123"
    })
    assert r.status_code == 204


# ── frontend serving ──────────────────────────────────────────────────────────

def test_serve_frontend_root(client: FlaskClient, tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "index.html").write_text("<h1>App</h1>")
    import torqued
    monkeypatch.setattr(torqued, "_DIST_DIR", str(tmp_path))
    r = client.get("/")
    assert r.status_code == 200
    assert b"App" in r.data


def test_serve_frontend_existing_file(client: FlaskClient, tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "index.html").write_text("<h1>App</h1>")
    (tmp_path / "app.js").write_text("var x = 1;")
    import torqued
    monkeypatch.setattr(torqued, "_DIST_DIR", str(tmp_path))
    r = client.get("/app.js")
    assert r.status_code == 200
    assert b"var x" in r.data


def test_serve_frontend_missing_path_returns_index(
    client: FlaskClient, tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "index.html").write_text("<h1>Fallback</h1>")
    import torqued
    monkeypatch.setattr(torqued, "_DIST_DIR", str(tmp_path))
    r = client.get("/some/deep/path")
    assert r.status_code == 200
    assert b"Fallback" in r.data


def test_unknown_api_route_returns_404_json(client: FlaskClient) -> None:
    # An unmatched /api/* path must not fall through to the SPA (which would be a
    # 200 of index.html that clients can't parse as JSON) — it returns a real 404.
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.json == {"error": "Not found"}


# ── db migrations ─────────────────────────────────────────────────────────────

def test_load_user_returns_none_for_deleted_user(client: FlaskClient) -> None:
    with get_db() as db:
        UserRepository(db).create("todelete", "pass")
    client.post("/api/auth/login", json={"username": "todelete", "password": "pass"})
    with get_db() as db:
        execute_sql(db, "DELETE FROM users WHERE username='todelete'")
    assert client.get("/api/vehicles").status_code == 401


def test_run_migrations_idempotent(auth_client: FlaskClient) -> None:
    """Calling run_migrations a second time skips already-applied migrations."""
    from torqued.db import run_migrations
    run_migrations()  # migrations already applied in fixture; this exercises the 'continue' branch


# ── maintenance mode ──────────────────────────────────────────────────────────

def test_maintenance_flag_serves_503(client: FlaskClient, monkeypatch, tmp_path: Path) -> None:
    flag = tmp_path / "MAINTENANCE"
    flag.write_text("")
    monkeypatch.setenv("MAINTENANCE_FILE", str(flag))
    r = client.get("/api/config")
    assert r.status_code == 503
    assert b"maintenance" in r.data.lower()


def test_no_maintenance_flag_serves_normally(client: FlaskClient, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MAINTENANCE_FILE", str(tmp_path / "absent"))
    assert client.get("/api/config").status_code == 200
