import os
import shutil
import tempfile
from collections.abc import Generator
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient


@pytest.fixture
def app() -> Generator[Flask, None, None]:
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    os.environ["DB_PATH"] = db_path
    upload_dir = tempfile.mkdtemp()
    os.environ["UPLOAD_DIR"] = upload_dir

    # Import after setting DB_PATH so the app picks up the temp database.
    from torqued import create_app

    application = create_app()
    application.config["TESTING"] = True
    application.config["WTF_CSRF_ENABLED"] = False

    yield application

    os.unlink(db_path)
    shutil.rmtree(upload_dir, ignore_errors=True)


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def garage(app: Flask) -> dict[str, Any]:
    """A garage that the auth/readonly/garage-admin fixtures are members of."""
    from torqued.db import get_db
    from torqued.repositories.garage_repository import GarageRepository

    with get_db() as db:
        return GarageRepository(db).create("Test Garage")


def make_member(username: str, password: str, role: str, garage: dict[str, Any]) -> dict[str, Any]:
    """Create a user and add them to the garage with the given role."""
    from torqued.db import get_db
    from torqued.repositories.garage_repository import GarageRepository
    from torqued.repositories.user_repository import UserRepository

    with get_db() as db:
        user = UserRepository(db).create(username, password)
        GarageRepository(db).add_member(garage["id"], user["id"], role)
    return user


def login(client: FlaskClient, username: str, password: str = "testpass") -> None:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.json


@pytest.fixture
def auth_client(client: FlaskClient, garage: dict[str, Any]) -> FlaskClient:
    """A normal (read-write) member of the test garage."""
    make_member("testuser", "testpass", "member", garage)
    login(client, "testuser")
    return client


@pytest.fixture
def readonly_client(client: FlaskClient, garage: dict[str, Any]) -> FlaskClient:
    """A read-only member of the test garage."""
    make_member("readonlyuser", "testpass", "readonly", garage)
    login(client, "readonlyuser")
    return client


@pytest.fixture
def garage_owner_client(client: FlaskClient, garage: dict[str, Any]) -> FlaskClient:
    """An owner of the test garage (not a site admin)."""
    make_member("garageowner", "testpass", "owner", garage)
    login(client, "garageowner")
    return client


@pytest.fixture
def admin_client(client: FlaskClient) -> FlaskClient:
    """A site admin with no explicit garage memberships."""
    from torqued.db import get_db
    from torqued.repositories.user_repository import UserRepository

    with get_db() as db:
        UserRepository(db).create("adminuser", "testpass", is_admin=True)

    login(client, "adminuser")
    return client
