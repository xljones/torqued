"""Tests for /api/garages and cross-garage tenancy enforcement."""
from typing import Any

from flask import Flask
from flask.testing import FlaskClient

from tests.conftest import login, make_member
from tests.test_vehicles import mk_vehicle
from torqued.db import get_db
from torqued.repositories.garage_repository import GarageRepository


def mk_garage(name: str = "Other Garage") -> dict[str, Any]:
    with get_db() as db:
        return GarageRepository(db).create(name)


# ── list ──────────────────────────────────────────────────────────────────────

def test_member_sees_only_their_garages(auth_client: FlaskClient) -> None:
    mk_garage()
    garages = auth_client.get("/api/garages").json
    assert [(g["name"], g["role"]) for g in garages] == [("Test Garage", "member")]
    assert garages[0]["member_count"] == 1
    assert garages[0]["vehicle_count"] == 0


def test_site_admin_sees_all_garages(admin_client: FlaskClient) -> None:
    mk_garage("A")
    mk_garage("B")
    garages = admin_client.get("/api/garages").json
    assert {g["name"] for g in garages} == {"A", "B"}
    assert all(g["role"] == "owner" for g in garages)


# ── create / rename / delete ──────────────────────────────────────────────────

def test_create_garage_site_admin_only(admin_client: FlaskClient) -> None:
    r = admin_client.post("/api/garages", json={"name": "New Garage"})
    assert r.status_code == 201
    assert r.json["name"] == "New Garage"
    assert admin_client.post("/api/garages", json={"name": "New Garage"}).status_code == 409
    assert admin_client.post("/api/garages", json={"name": " "}).status_code == 400


def test_create_garage_forbidden_for_members(garage_owner_client: FlaskClient) -> None:
    # Even a garage owner can't create garages — only site admins can.
    assert garage_owner_client.post("/api/garages", json={"name": "X"}).status_code == 403


def test_rename_garage_as_garage_owner(garage_owner_client: FlaskClient) -> None:
    garage_id = garage_owner_client.get("/api/garages").json[0]["id"]
    r = garage_owner_client.put(f"/api/garages/{garage_id}", json={"name": "Renamed"})
    assert r.status_code == 200
    assert r.json["name"] == "Renamed"


def test_rename_garage_validation(garage_owner_client: FlaskClient) -> None:
    garage_id = garage_owner_client.get("/api/garages").json[0]["id"]
    assert garage_owner_client.put(f"/api/garages/{garage_id}", json={}).status_code == 400
    assert garage_owner_client.put("/api/garages/999", json={"name": "X"}).status_code == 404
    other = mk_garage()
    r = garage_owner_client.put(f"/api/garages/{garage_id}", json={"name": other["name"]})
    assert r.status_code == 409


def test_rename_garage_forbidden_for_plain_member(auth_client: FlaskClient) -> None:
    garage_id = auth_client.get("/api/garages").json[0]["id"]
    assert auth_client.put(f"/api/garages/{garage_id}", json={"name": "X"}).status_code == 403


def test_delete_garage_site_admin_only(
    garage_owner_client: FlaskClient, app: Flask
) -> None:
    garage_id = garage_owner_client.get("/api/garages").json[0]["id"]
    assert garage_owner_client.delete(f"/api/garages/{garage_id}").status_code == 403


def test_delete_garage_cascades(admin_client: FlaskClient) -> None:
    garage = mk_garage()
    v = mk_vehicle(admin_client, garage_id=garage["id"])
    assert admin_client.delete(f"/api/garages/{garage['id']}").status_code == 204
    assert admin_client.get(f"/api/vehicles/{v['id']}").status_code == 404
    assert admin_client.delete("/api/garages/999").status_code == 404


# ── members ───────────────────────────────────────────────────────────────────

def test_members_visible_to_members(auth_client: FlaskClient) -> None:
    garage_id = auth_client.get("/api/garages").json[0]["id"]
    members = auth_client.get(f"/api/garages/{garage_id}/members").json
    assert [(m["username"], m["role"]) for m in members] == [("testuser", "member")]


def test_members_hidden_from_non_members(auth_client: FlaskClient) -> None:
    other = mk_garage()
    assert auth_client.get(f"/api/garages/{other['id']}/members").status_code == 403
    assert auth_client.get("/api/garages/999/members").status_code == 404


def test_add_member(garage_owner_client: FlaskClient, garage: dict[str, Any]) -> None:
    with get_db() as db:
        from torqued.repositories.user_repository import UserRepository
        UserRepository(db).create("newbie", "testpass")
    r = garage_owner_client.post(f"/api/garages/{garage['id']}/members",
                                 json={"username": "newbie", "role": "readonly"})
    assert r.status_code == 201
    assert r.json["username"] == "newbie"
    assert r.json["role"] == "readonly"
    # duplicate
    assert garage_owner_client.post(f"/api/garages/{garage['id']}/members",
                                    json={"username": "newbie"}).status_code == 409


def test_add_member_validation(garage_owner_client: FlaskClient, garage: dict[str, Any]) -> None:
    url = f"/api/garages/{garage['id']}/members"
    assert garage_owner_client.post(url, json={}).status_code == 400
    assert garage_owner_client.post(url, json={"username": "x", "role": "boss"}).status_code == 400
    assert garage_owner_client.post(url, json={"username": "ghost"}).status_code == 404
    assert garage_owner_client.post("/api/garages/999/members",
                                    json={"username": "x"}).status_code == 404


def test_add_member_requires_garage_owner(auth_client: FlaskClient, garage: dict[str, Any]) -> None:
    r = auth_client.post(f"/api/garages/{garage['id']}/members", json={"username": "x"})
    assert r.status_code == 403


def test_set_member_role(garage_owner_client: FlaskClient, garage: dict[str, Any]) -> None:
    member = make_member("colleague", "testpass", "member", garage)
    url = f"/api/garages/{garage['id']}/members/{member['id']}"
    r = garage_owner_client.put(url, json={"role": "owner"})
    assert r.status_code == 200
    assert ("colleague", "owner") in [(m["username"], m["role"]) for m in r.json]
    assert garage_owner_client.put(url, json={"role": "boss"}).status_code == 400
    assert garage_owner_client.put(f"/api/garages/{garage['id']}/members/999",
                                   json={"role": "member"}).status_code == 404


def test_set_member_role_requires_garage_owner(
    auth_client: FlaskClient, garage: dict[str, Any]
) -> None:
    assert auth_client.put(f"/api/garages/{garage['id']}/members/1",
                           json={"role": "member"}).status_code == 403


def test_remove_member(garage_owner_client: FlaskClient, garage: dict[str, Any]) -> None:
    member = make_member("leaver", "testpass", "member", garage)
    url = f"/api/garages/{garage['id']}/members/{member['id']}"
    assert garage_owner_client.delete(url).status_code == 204
    assert garage_owner_client.delete(url).status_code == 404


def test_remove_member_requires_garage_owner(
    auth_client: FlaskClient, garage: dict[str, Any]
) -> None:
    assert auth_client.delete(f"/api/garages/{garage['id']}/members/1").status_code == 403


# ── tenancy enforcement across garages ────────────────────────────────────────

def test_cross_garage_isolation(client: FlaskClient, garage: dict[str, Any]) -> None:
    """A member of garage A can't see or touch garage B's data at all."""
    other = mk_garage()
    make_member("alice", "testpass", "member", garage)
    make_member("bob", "testpass", "member", other)

    login(client, "bob")
    foreign = mk_vehicle(client, garage_id=other["id"])
    client.post(f"/api/vehicles/{foreign['id']}/services",
                json={"date": "2025-01-01", "title": "Oil", "next_due_date": "2030-01-01"})

    login(client, "alice")
    assert client.get("/api/vehicles").json == []
    assert client.get(f"/api/vehicles/{foreign['id']}").status_code == 404
    assert client.put(f"/api/vehicles/{foreign['id']}",
                      json={"name": "Hacked"}).status_code == 404
    assert client.delete(f"/api/vehicles/{foreign['id']}").status_code == 404
    assert client.get(f"/api/vehicles/{foreign['id']}/services").status_code == 404
    assert client.get(f"/api/vehicles/{foreign['id']}/mileage").status_code == 404
    assert client.get("/api/services").json == []
    assert client.get("/api/reminders").json == []
    assert client.get("/api/search?q=Street").json == []
    assert client.get("/api/services?garage_id=" + str(other["id"])).status_code == 404


def test_readonly_member_blocked_from_garage_writes(
    readonly_client: FlaskClient, garage: dict[str, Any], app: Flask
) -> None:
    """Read-only members can view everything but write nothing."""
    with get_db() as db:
        from torqued.repositories.vehicle_repository import VehicleRepository
        v = VehicleRepository(db).create(garage["id"], {"name": "Shared bike"})

    # Reads are fine
    assert readonly_client.get("/api/vehicles").status_code == 200
    assert readonly_client.get(f"/api/vehicles/{v['id']}").status_code == 200

    # Writes are blocked with 403 (not 404 — they can see it)
    assert readonly_client.put(f"/api/vehicles/{v['id']}",
                               json={"name": "Nope"}).status_code == 403
    assert readonly_client.delete(f"/api/vehicles/{v['id']}").status_code == 403
    assert readonly_client.put(f"/api/vehicles/{v['id']}/specs",
                               json={"specs": []}).status_code == 403
    assert readonly_client.post(f"/api/vehicles/{v['id']}/revert/1").status_code == 403
    assert readonly_client.post(f"/api/vehicles/{v['id']}/services",
                                json={"date": "2025-01-01", "title": "Oil"}).status_code == 403
    assert readonly_client.post(f"/api/vehicles/{v['id']}/odometer",
                                json={"date": "2025-01-01", "odometer": 1}).status_code == 403


def test_user_with_no_garages_sees_nothing(client: FlaskClient, app: Flask) -> None:
    """Endpoints all return empty results for a user with no memberships."""
    from torqued.repositories.user_repository import UserRepository
    with get_db() as db:
        UserRepository(db).create("nomad", "testpass")
    login(client, "nomad")
    assert client.get("/api/garages").json == []
    assert client.get("/api/vehicles").json == []
    assert client.get("/api/services").json == []
    assert client.get("/api/services/performers").json == []
    assert client.get("/api/reminders").json == []
    assert client.get("/api/search?q=x").json == []
    assert client.get("/api/export/services").data.decode().strip() == ""


def test_readonly_blocked_from_service_and_photo_writes(
    readonly_client: FlaskClient, garage: dict[str, Any]
) -> None:
    """Read-only write checks on service/odometer/photo item routes."""
    import io
    from torqued.repositories.odometer_log_repository import OdometerLogRepository
    from torqued.repositories.photo_repository import PhotoRepository
    from torqued.repositories.service_log_repository import ServiceLogRepository
    from torqued.repositories.vehicle_repository import VehicleRepository
    with get_db() as db:
        v = VehicleRepository(db).create(garage["id"], {"name": "Shared bike"})
        log = ServiceLogRepository(db).create(
            {"vehicle_id": v["id"], "date": "2025-01-01", "title": "Oil"}
        )
        odo = OdometerLogRepository(db).create(v["id"], "2025-01-01", 100.0, "km")
        photo = PhotoRepository(db).create(v["id"], "x.png")

    body = {"date": "2025-01-01", "title": "Oil"}
    assert readonly_client.put(f"/api/services/{log['id']}", json=body).status_code == 403
    assert readonly_client.delete(f"/api/services/{log['id']}").status_code == 403
    assert readonly_client.post(f"/api/services/{log['id']}/revert/1").status_code == 403
    assert readonly_client.get(f"/api/services/{log['id']}/history").status_code == 200
    assert readonly_client.delete(f"/api/odometer/{odo['id']}").status_code == 403
    assert readonly_client.put(f"/api/photos/{photo['id']}",
                               json={"caption": "x"}).status_code == 403
    assert readonly_client.delete(f"/api/photos/{photo['id']}").status_code == 403
    r = readonly_client.post(
        f"/api/vehicles/{v['id']}/photos",
        data={"file": (io.BytesIO(b"img"), "a.png")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 403


def test_garage_repository_get_by_name(app: Flask) -> None:
    with get_db() as db:
        repo = GarageRepository(db)
        created = repo.create("Lookup Garage")
        assert repo.get_by_name("lookup garage")["id"] == created["id"]
        assert repo.get_by_name("missing") is None


def test_site_admin_sees_everything(admin_client: FlaskClient, garage: dict[str, Any]) -> None:
    other = mk_garage()
    mk_vehicle(admin_client, garage_id=garage["id"], name="In A")
    mk_vehicle(admin_client, garage_id=other["id"], name="In B")
    names = {v["name"] for v in admin_client.get("/api/vehicles").json}
    assert names == {"In A", "In B"}
