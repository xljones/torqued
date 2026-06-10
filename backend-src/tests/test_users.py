from flask.testing import FlaskClient

from torqued.db import get_db
from torqued.repositories.user_repository import UserRepository


def test_list_users_requires_auth(client: FlaskClient) -> None:
    assert client.get("/api/users").status_code == 401


def test_list_users_requires_admin(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/users").status_code == 403


def test_list_users(admin_client: FlaskClient) -> None:
    r = admin_client.get("/api/users")
    assert r.status_code == 200
    assert isinstance(r.json, list)
    assert any(u["username"] == "adminuser" for u in r.json)


def test_create_user_requires_admin(auth_client: FlaskClient) -> None:
    r = auth_client.post("/api/users", json={"username": "newuser", "password": "securepass"})
    assert r.status_code == 403


def test_create_readonly_user(admin_client: FlaskClient) -> None:
    r = admin_client.post("/api/users", json={"username": "rouser", "password": "securepass"})
    assert r.status_code == 201
    assert r.json["username"] == "rouser"
    assert r.json["is_readonly"] is True
    assert r.json["is_admin"] is False


def test_create_normal_user(admin_client: FlaskClient) -> None:
    r = admin_client.post(
        "/api/users", json={"username": "normaluser", "password": "securepass", "is_readonly": False}
    )
    assert r.status_code == 201
    assert r.json["is_readonly"] is False
    assert r.json["is_admin"] is False


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
    assert admin_client.post("/api/users", json={"username": "dup", "password": "pass"}).status_code == 409


def test_delete_user_requires_admin(auth_client: FlaskClient) -> None:
    with get_db() as db:
        other = UserRepository(db).create("victim", "pass", is_readonly=True)
    assert auth_client.delete(f"/api/users/{other['id']}").status_code == 403


def test_delete_readonly_user(admin_client: FlaskClient) -> None:
    r = admin_client.post("/api/users", json={"username": "readonly1", "password": "pass"})
    user_id = r.json["id"]
    assert admin_client.delete(f"/api/users/{user_id}").status_code == 204


def test_delete_normal_user(admin_client: FlaskClient) -> None:
    with get_db() as db:
        other = UserRepository(db).create("normalvictim", "pass", is_readonly=False)
    assert admin_client.delete(f"/api/users/{other['id']}").status_code == 204


def test_delete_user_not_found(admin_client: FlaskClient) -> None:
    assert admin_client.delete("/api/users/9999").status_code == 404


def test_delete_own_account_forbidden(admin_client: FlaskClient) -> None:
    me = admin_client.get("/api/auth/me").json
    assert admin_client.delete(f"/api/users/{me['id']}").status_code == 400


def test_delete_admin_account_forbidden(admin_client: FlaskClient) -> None:
    with get_db() as db:
        other = UserRepository(db).create("otheradmin", "pass", is_admin=True)
    r = admin_client.delete(f"/api/users/{other['id']}")
    assert r.status_code == 403


def test_user_repository_rename() -> None:
    import os, tempfile
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    os.environ["DB_PATH"] = db_path
    try:
        from torqued.db import run_migrations, get_db
        run_migrations()
        with get_db() as db:
            user = UserRepository(db).create("original", "pass")
            UserRepository(db).rename(user["id"], "renamed")
            updated = UserRepository(db).get_by_id(user["id"])
        assert updated["username"] == "renamed"
    finally:
        os.unlink(db_path)
        os.environ.pop("DB_PATH", None)
