"""Tests for /api/users: site-admin user management."""
from typing import Any

from flask.testing import FlaskClient

from tests.conftest import make_member
from torqued.db import get_db
from torqued.repositories.user_repository import UserRepository


def test_list_users_requires_auth(client: FlaskClient) -> None:
    assert client.get("/api/users").status_code == 401


def test_list_users_requires_admin(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/users").status_code == 403


def test_list_users_includes_memberships(
    admin_client: FlaskClient, garage: dict[str, Any]
) -> None:
    make_member("wrench", "testpass", "owner", garage)
    r = admin_client.get("/api/users")
    assert r.status_code == 200
    wrench = next(u for u in r.json if u["username"] == "wrench")
    assert wrench["memberships"] == [
        {"garage_id": garage["id"], "garage_name": "Test Garage", "role": "owner"}
    ]
    me = next(u for u in r.json if u["username"] == "adminuser")
    assert me["memberships"] == []


def test_create_user_requires_admin(auth_client: FlaskClient) -> None:
    r = auth_client.post("/api/users", json={"username": "newuser", "password": "securepass"})
    assert r.status_code == 403


def test_create_user_without_garage(admin_client: FlaskClient) -> None:
    r = admin_client.post("/api/users", json={"username": "loner", "password": "securepass"})
    assert r.status_code == 201
    assert r.json["username"] == "loner"
    assert r.json["is_admin"] is False
    assert r.json["memberships"] == []


def test_create_user_with_garage_and_role(
    admin_client: FlaskClient, garage: dict[str, Any]
) -> None:
    r = admin_client.post("/api/users", json={
        "username": "spanner", "password": "securepass",
        "garage_id": garage["id"], "role": "readonly",
    })
    assert r.status_code == 201
    assert r.json["memberships"] == [
        {"garage_id": garage["id"], "garage_name": "Test Garage", "role": "readonly"}
    ]


def test_create_site_admin(admin_client: FlaskClient) -> None:
    r = admin_client.post("/api/users", json={
        "username": "boss", "password": "securepass", "is_admin": True,
    })
    assert r.status_code == 201
    assert r.json["is_admin"] is True


def test_create_user_bad_role(admin_client: FlaskClient, garage: dict[str, Any]) -> None:
    r = admin_client.post("/api/users", json={
        "username": "x", "password": "y", "garage_id": garage["id"], "role": "boss",
    })
    assert r.status_code == 400


def test_create_user_unknown_garage(admin_client: FlaskClient) -> None:
    r = admin_client.post("/api/users", json={
        "username": "x", "password": "y", "garage_id": 999,
    })
    assert r.status_code == 400


def test_create_user_with_ttl(admin_client: FlaskClient) -> None:
    r = admin_client.post("/api/users", json={
        "username": "tempuser", "password": "securepass", "ttl_days": 7
    })
    assert r.status_code == 201
    assert r.json["expires_at"] is not None


def test_create_user_missing_fields(admin_client: FlaskClient) -> None:
    assert admin_client.post("/api/users", json={"username": "x"}).status_code == 400
    assert admin_client.post("/api/users", json={"password": "x"}).status_code == 400


def test_create_user_invalid_ttl(admin_client: FlaskClient) -> None:
    r = admin_client.post("/api/users", json={
        "username": "u", "password": "pass", "ttl_days": -1
    })
    assert r.status_code == 400


def test_create_user_non_integer_ttl(admin_client: FlaskClient) -> None:
    r = admin_client.post("/api/users", json={
        "username": "u", "password": "pass", "ttl_days": "abc"
    })
    assert r.status_code == 400


def test_create_user_duplicate_username(admin_client: FlaskClient) -> None:
    admin_client.post("/api/users", json={"username": "dup", "password": "pass"})
    assert admin_client.post(
        "/api/users", json={"username": "dup", "password": "pass"}
    ).status_code == 409


def test_reset_password(admin_client: FlaskClient) -> None:
    created = admin_client.post(
        "/api/users", json={"username": "forgetful", "password": "oldpass"}
    ).json
    assert admin_client.put(
        f"/api/users/{created['id']}/password", json={"password": "newpass123"}
    ).status_code == 204
    # Old password no longer works; the new one does
    admin_client.post("/api/auth/logout")
    assert admin_client.post("/api/auth/login", json={
        "username": "forgetful", "password": "oldpass",
    }).status_code == 401
    assert admin_client.post("/api/auth/login", json={
        "username": "forgetful", "password": "newpass123",
    }).status_code == 200


def test_reset_password_validation(admin_client: FlaskClient) -> None:
    created = admin_client.post(
        "/api/users", json={"username": "forgetful", "password": "oldpass"}
    ).json
    assert admin_client.put(
        f"/api/users/{created['id']}/password", json={"password": "tiny"}
    ).status_code == 400
    assert admin_client.put(
        f"/api/users/{created['id']}/password", json={}
    ).status_code == 400
    assert admin_client.put(
        "/api/users/999/password", json={"password": "newpass123"}
    ).status_code == 404


def test_reset_password_requires_admin(auth_client: FlaskClient) -> None:
    assert auth_client.put(
        "/api/users/1/password", json={"password": "newpass123"}
    ).status_code == 403


def test_reset_password_other_admin_forbidden(admin_client: FlaskClient) -> None:
    other = admin_client.post("/api/users", json={
        "username": "otheradmin2", "password": "securepass", "is_admin": True,
    }).json
    r = admin_client.put(f"/api/users/{other['id']}/password", json={"password": "newpass123"})
    assert r.status_code == 403


def test_reset_own_password_allowed(admin_client: FlaskClient) -> None:
    me = admin_client.get("/api/auth/me").json
    assert admin_client.put(
        f"/api/users/{me['id']}/password", json={"password": "newpass123"}
    ).status_code == 204


def test_delete_user_requires_admin(auth_client: FlaskClient) -> None:
    with get_db() as db:
        other = UserRepository(db).create("victim", "pass")
    assert auth_client.delete(f"/api/users/{other['id']}").status_code == 403


def test_delete_user(admin_client: FlaskClient) -> None:
    r = admin_client.post("/api/users", json={"username": "victim", "password": "pass"})
    user_id = r.json["id"]
    assert admin_client.delete(f"/api/users/{user_id}").status_code == 204
    assert admin_client.delete(f"/api/users/{user_id}").status_code == 404


def test_delete_own_account_forbidden(admin_client: FlaskClient) -> None:
    me = admin_client.get("/api/auth/me").json
    assert admin_client.delete(f"/api/users/{me['id']}").status_code == 400


def test_delete_admin_account_forbidden(admin_client: FlaskClient) -> None:
    with get_db() as db:
        other = UserRepository(db).create("otheradmin", "pass", is_admin=True)
    r = admin_client.delete(f"/api/users/{other['id']}")
    assert r.status_code == 403


def test_user_repository_rename() -> None:
    import os
    import tempfile
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    os.environ["DB_PATH"] = db_path
    try:
        from torqued.db import get_db, run_migrations
        run_migrations()
        with get_db() as db:
            user = UserRepository(db).create("original", "pass")
            UserRepository(db).rename(user["id"], "renamed")
            updated = UserRepository(db).get_by_id(user["id"])
        assert updated["username"] == "renamed"
    finally:
        os.unlink(db_path)
        os.environ.pop("DB_PATH", None)
