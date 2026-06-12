from flask import Flask
from flask.testing import FlaskClient

from torqued.db import get_db
from torqued.repositories.user_repository import UserRepository


def test_login_success(client: FlaskClient, app: Flask) -> None:
    with app.app_context():
        with get_db() as db:
            UserRepository(db).create("alice", "secret")
    r = client.post("/api/auth/login", json={"username": "alice", "password": "secret"})
    assert r.status_code == 200
    assert r.json["username"] == "alice"
    assert r.json["memberships"] == []


def test_login_wrong_password(client: FlaskClient, app: Flask) -> None:
    with app.app_context():
        with get_db() as db:
            UserRepository(db).create("alice", "secret")
    r = client.post("/api/auth/login", json={"username": "alice", "password": "wrong"})
    assert r.status_code == 401


def test_login_missing_fields(client: FlaskClient) -> None:
    assert client.post("/api/auth/login", json={"username": "alice"}).status_code == 400


def test_login_expired_account(client: FlaskClient, app: Flask) -> None:
    with app.app_context():
        with get_db() as db:
            user = UserRepository(db).create("expired", "pass")
            db.execute(
                "UPDATE users SET expires_at=? WHERE id=?",
                ("2000-01-01T00:00:00+00:00", user["id"]),
            )
    r = client.post("/api/auth/login", json={"username": "expired", "password": "pass"})
    assert r.status_code == 401
    assert "expired" in r.json["error"].lower()


def test_me_unauthenticated(client: FlaskClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_me_authenticated(auth_client: FlaskClient) -> None:
    r = auth_client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json["username"] == "testuser"
    assert r.json["memberships"] == [
        {"garage_id": 1, "garage_name": "Test Garage", "role": "member"}
    ]


def test_logout(auth_client: FlaskClient) -> None:
    assert auth_client.post("/api/auth/logout").status_code == 204
    assert auth_client.get("/api/auth/me").status_code == 401


def test_login_case_insensitive(client: FlaskClient, app: Flask) -> None:
    with app.app_context():
        with get_db() as db:
            UserRepository(db).create("Scarlett", "secret")
    assert client.post("/api/auth/login", json={"username": "scarlett", "password": "secret"}).status_code == 200
    assert client.post("/api/auth/login", json={"username": "SCARLETT", "password": "secret"}).status_code == 200


def test_login_preserves_stored_username(client: FlaskClient, app: Flask) -> None:
    with app.app_context():
        with get_db() as db:
            UserRepository(db).create("Scarlett", "secret")
    r = client.post("/api/auth/login", json={"username": "scarlett", "password": "secret"})
    assert r.json["username"] == "Scarlett"


def test_logout_readonly_user(readonly_client: FlaskClient) -> None:
    assert readonly_client.post("/api/auth/logout").status_code == 204
    assert readonly_client.get("/api/auth/me").status_code == 401


def test_change_password_success(auth_client: FlaskClient) -> None:
    r = auth_client.put("/api/auth/password", json={
        "current_password": "testpass", "new_password": "newpass123"
    })
    assert r.status_code == 204


def test_change_password_wrong_current(auth_client: FlaskClient) -> None:
    r = auth_client.put("/api/auth/password", json={
        "current_password": "wrongpass", "new_password": "newpass123"
    })
    assert r.status_code == 403


def test_change_password_missing_fields(auth_client: FlaskClient) -> None:
    r = auth_client.put("/api/auth/password", json={"current_password": "testpass"})
    assert r.status_code == 400


def test_change_password_too_short(auth_client: FlaskClient) -> None:
    r = auth_client.put("/api/auth/password", json={
        "current_password": "testpass", "new_password": "abc"
    })
    assert r.status_code == 400
