"""Tests for the DVSA MOT history integration: client, storage, and routes."""
import json
import urllib.error
from datetime import date, timedelta
from typing import Any

import pytest
from flask.testing import FlaskClient

from tests.test_vehicles import mk_vehicle
from torqued import mot

SAMPLE: dict[str, Any] = {
    "registration": "A1XYZ",
    "make": "VOLKSWAGEN",
    "model": "PASSAT",
    "firstUsedDate": "2003-11-21",
    "fuelType": "Diesel",
    "primaryColour": "Blue",
    "registrationDate": "2003-11-21",
    "manufactureDate": "2003-11-21",
    "engineSize": "1896",
    "hasOutstandingRecall": "Unknown",
    "motTests": [
        {
            "completedDate": "2024-11-05T10:01:00.000Z", "testResult": "PASSED",
            "expiryDate": "2025-11-04", "odometerValue": 100, "odometerUnit": "MI",
            "odometerResultType": "READ", "motTestNumber": "1234", "dataSource": "DVSA",
            "defects": [{"text": "Tyre worn close to limit", "type": "ADVISORY", "dangerous": False}],
        },
        {
            "completedDate": "2023-10-30T09:00:00.000Z", "testResult": "FAILED",
            "expiryDate": None, "odometerValue": 200, "odometerUnit": "KM",
            "odometerResultType": "READ", "motTestNumber": "1233", "dataSource": "DVSA",
            "location": "Test Lane ATF",
            "defects": [{"text": "Brake pipe corroded", "type": "MAJOR", "dangerous": True}],
        },
        {
            "completedDate": "2022-10-01T09:00:00.000Z", "testResult": "PASSED",
            "expiryDate": "2023-10-31", "odometerValue": None, "odometerUnit": None,
            "odometerResultType": "NO_ODOMETER", "motTestNumber": "1232", "dataSource": "DVSA",
        },
    ],
}

NEW_REG: dict[str, Any] = {
    "registration": "A2XYZ",
    "make": "PORSCHE",
    "model": "CAYMAN",
    "manufactureYear": 2024,
    "fuelType": "Petrol",
    "primaryColour": "White",
    "registrationDate": "2024-09-01",
    "manufactureDate": "2024-08-01",
    "motTestDueDate": "2027-09-01",
    "hasOutstandingRecall": "No",
}


@pytest.fixture(autouse=True)
def reset_token_cache() -> None:
    mot._token_cache.update({"token": None, "expires": 0.0})


@pytest.fixture
def mot_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOT_CLIENT_ID", "cid")
    monkeypatch.setenv("MOT_CLIENT_SECRET", "secret")
    monkeypatch.setenv("MOT_TOKEN_URL", "https://login.example/token")
    monkeypatch.setenv("MOT_API_KEY", "key")


class FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: Any) -> bool:
        return False


# ── client ────────────────────────────────────────────────────────────────────

def test_is_configured(monkeypatch: pytest.MonkeyPatch, mot_env: None) -> None:
    assert mot.is_configured() is True
    monkeypatch.delenv("MOT_API_KEY")
    assert mot.is_configured() is False


def test_normalise_registration() -> None:
    assert mot.normalise_registration("a1 xyz") == "A1XYZ"


def test_fetch_vehicle_success(monkeypatch: pytest.MonkeyPatch, mot_env: None) -> None:
    calls: list[str] = []

    def fake_urlopen(req: Any, timeout: int = 0) -> FakeResponse:
        calls.append(req.full_url)
        if req.full_url == "https://login.example/token":
            return FakeResponse({"access_token": "tok", "expires_in": 3600})
        assert req.headers["Authorization"] == "Bearer tok"
        assert req.headers["X-api-key"] == "key"
        return FakeResponse(SAMPLE)

    monkeypatch.setattr(mot.urllib.request, "urlopen", fake_urlopen)
    assert mot.fetch_vehicle("a1 xyz")["registration"] == "A1XYZ"
    assert calls == ["https://login.example/token", mot.API_BASE + "A1XYZ"]
    # The token is cached: a second fetch skips the token endpoint
    mot.fetch_vehicle("A1XYZ")
    assert calls.count("https://login.example/token") == 1


def test_fetch_vehicle_not_found(monkeypatch: pytest.MonkeyPatch, mot_env: None) -> None:
    mot._token_cache.update({"token": "tok", "expires": 9e12})

    def fake_urlopen(req: Any, timeout: int = 0) -> FakeResponse:
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", None, None)  # type: ignore[arg-type]

    monkeypatch.setattr(mot.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(mot.MotError) as e:
        mot.fetch_vehicle("XX99XXX")
    assert e.value.status == 404


def test_fetch_vehicle_api_error(monkeypatch: pytest.MonkeyPatch, mot_env: None) -> None:
    mot._token_cache.update({"token": "tok", "expires": 9e12})

    def fake_urlopen(req: Any, timeout: int = 0) -> FakeResponse:
        raise urllib.error.HTTPError(req.full_url, 500, "Server Error", None, None)  # type: ignore[arg-type]

    monkeypatch.setattr(mot.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(mot.MotError) as e:
        mot.fetch_vehicle("A1XYZ")
    assert e.value.status == 502


def test_fetch_vehicle_unreachable(monkeypatch: pytest.MonkeyPatch, mot_env: None) -> None:
    mot._token_cache.update({"token": "tok", "expires": 9e12})

    def fake_urlopen(req: Any, timeout: int = 0) -> FakeResponse:
        raise OSError("no route to host")

    monkeypatch.setattr(mot.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(mot.MotError) as e:
        mot.fetch_vehicle("A1XYZ")
    assert e.value.status == 502


def test_token_auth_failure(monkeypatch: pytest.MonkeyPatch, mot_env: None) -> None:
    def fake_urlopen(req: Any, timeout: int = 0) -> FakeResponse:
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", None, None)  # type: ignore[arg-type]

    monkeypatch.setattr(mot.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(mot.MotError, match="authentication failed"):
        mot.fetch_vehicle("A1XYZ")


def test_token_endpoint_unreachable(monkeypatch: pytest.MonkeyPatch, mot_env: None) -> None:
    def fake_urlopen(req: Any, timeout: int = 0) -> FakeResponse:
        raise OSError("timed out")

    monkeypatch.setattr(mot.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(mot.MotError, match="token endpoint"):
        mot.fetch_vehicle("A1XYZ")


def test_to_baseline_derives_year_from_registration_date() -> None:
    # No manufactureYear / manufactureDate / firstUsedDate → falls through to registrationDate
    b = mot.to_baseline({"registration": "X", "registrationDate": "2010-06-01"})
    assert b["year"] == 2010


def test_to_baseline_year_none_without_dates() -> None:
    assert mot.to_baseline({"registration": "X"})["year"] is None


# ── routes ────────────────────────────────────────────────────────────────────

def test_get_mot_requires_auth(client: FlaskClient) -> None:
    assert client.get("/api/vehicles/1/mot").status_code == 401


def test_mot_status(auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    for v in ("MOT_CLIENT_ID", "MOT_CLIENT_SECRET", "MOT_TOKEN_URL", "MOT_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    assert auth_client.get("/api/mot/status").json == {"configured": False}
    monkeypatch.setenv("MOT_CLIENT_ID", "c")
    monkeypatch.setenv("MOT_CLIENT_SECRET", "s")
    monkeypatch.setenv("MOT_TOKEN_URL", "u")
    monkeypatch.setenv("MOT_API_KEY", "k")
    assert auth_client.get("/api/mot/status").json == {"configured": True}


def test_lookup_requires_auth(client: FlaskClient) -> None:
    assert client.get("/api/mot/lookup/A1XYZ").status_code == 401


def test_lookup_unconfigured(auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    for v in ("MOT_CLIENT_ID", "MOT_CLIENT_SECRET", "MOT_TOKEN_URL", "MOT_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    assert auth_client.get("/api/mot/lookup/A1XYZ").status_code == 503


def test_lookup_success(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    r = auth_client.get("/api/mot/lookup/A1%20XYZ")
    assert r.status_code == 200
    assert r.json["configured"] is True
    assert r.json["mot_baseline"]["make"] == "VOLKSWAGEN"
    assert r.json["mot_baseline"]["year"] == 2003


def test_lookup_relays_dvsa_error(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    def boom(reg: str) -> dict[str, Any]:
        raise mot.MotError("No MOT record found", 404)

    monkeypatch.setattr(mot, "fetch_vehicle", boom)
    assert auth_client.get("/api/mot/lookup/XX99XXX").status_code == 404


def test_get_mot_vehicle_404(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/vehicles/999/mot").status_code == 404


def test_get_mot_empty(auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    for v in ("MOT_CLIENT_ID", "MOT_CLIENT_SECRET", "MOT_TOKEN_URL", "MOT_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    veh = mk_vehicle(auth_client, registration="A1 XYZ")
    r = auth_client.get(f"/api/vehicles/{veh['id']}/mot")
    assert r.status_code == 200
    assert r.json == {"configured": False, "mot": None}


def test_refresh_vehicle_404(auth_client: FlaskClient) -> None:
    assert auth_client.post("/api/vehicles/999/mot/refresh").status_code == 404


def test_refresh_readonly_403(readonly_client: FlaskClient, garage: dict[str, Any]) -> None:
    from torqued.db import get_db
    from torqued.repositories.vehicle_repository import VehicleRepository

    with get_db() as db:
        v = VehicleRepository(db).create(garage["id"], {"name": "Shared bike"})
    assert readonly_client.post(f"/api/vehicles/{v['id']}/mot/refresh").status_code == 403


def test_refresh_without_registration(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    r = auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    assert r.status_code == 400
    assert "registration" in r.json["error"]


def test_refresh_unconfigured(auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    for env in ("MOT_CLIENT_ID", "MOT_CLIENT_SECRET", "MOT_TOKEN_URL", "MOT_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    v = mk_vehicle(auth_client, registration="A1 XYZ")
    r = auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    assert r.status_code == 503


def test_refresh_relays_dvsa_error(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    def boom(reg: str) -> dict[str, Any]:
        raise mot.MotError("No MOT record found for registration A1XYZ", 404)

    monkeypatch.setattr(mot, "fetch_vehicle", boom)
    v = mk_vehicle(auth_client, registration="A1 XYZ")
    r = auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    assert r.status_code == 404
    assert "No MOT record" in r.json["error"]


def test_refresh_stores_and_syncs(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    v = mk_vehicle(auth_client, registration="A1 XYZ", odometer_unit="mi")
    # A pre-existing manual log must survive the refresh
    auth_client.post(f"/api/vehicles/{v['id']}/odometer", json={
        "date": "2024-01-01", "odometer": 50, "unit": "mi", "note": "manual",
    })

    r = auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    assert r.status_code == 200
    assert "odometer_logs_synced" not in r.json

    m = r.json["mot"]
    assert m["make"] == "VOLKSWAGEN"
    assert m["has_outstanding_recall"] == "Unknown"
    assert m["raw"]["registration"] == "A1XYZ"
    assert [t["mot_test_number"] for t in m["tests"]] == ["1234", "1233", "1232"]
    assert m["tests"][0]["odometer_unit"] == "mi"
    assert m["tests"][1]["odometer_unit"] == "km"
    assert m["tests"][1]["location"] == "Test Lane ATF"
    assert m["tests"][0]["defects"][0]["type"] == "ADVISORY"
    assert m["tests"][2]["defects"] == []
    # The MOT card's expiry tile is now resolved server-side (latest test's expiry).
    assert m["expiry"]["expiry_date"] == "2025-11-04"
    assert m["expiry"]["status"] == "expired"  # 2025-11-04 is in the past

    # Manual log is the only entry in odometer_logs; MOT readings are not copied
    logs = auth_client.get(f"/api/vehicles/{v['id']}/odometer").json
    assert [(log["source"], log["date"]) for log in logs] == [("manual", "2024-01-01")]

    # Refresh is idempotent: still just the one manual log
    r2 = auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    assert r2.status_code == 200
    assert len(auth_client.get(f"/api/vehicles/{v['id']}/odometer").json) == 1

    # The mileage series queries mot_tests directly — MOT readings appear without duplication
    series = auth_client.get(f"/api/vehicles/{v['id']}/mileage").json
    assert [p["source"] for p in series] == ["mot", "manual", "mot"]
    mot_entry = next(p for p in series if p["source"] == "mot" and p["note"] == "MOT test (PASSED)")
    assert mot_entry["odometer_km"] == pytest.approx(160.9344)  # 100 mi converted
    km_entry = next(p for p in series if p["source"] == "mot" and p["note"] == "MOT test (FAILED)")
    assert km_entry["odometer_km"] == 200.0  # already km

    # GET returns the stored snapshot
    g = auth_client.get(f"/api/vehicles/{v['id']}/mot")
    assert g.json["configured"] is True
    assert g.json["mot"]["registration"] == "A1XYZ"


def test_update_disconnect_mot_clears_stored_data(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    v = mk_vehicle(auth_client, registration="A1 XYZ")
    auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    assert auth_client.get(f"/api/vehicles/{v['id']}/mot").json["mot"] is not None

    # Changing the plate and asking to disconnect drops the snapshot, its tests and the baseline.
    body = {"name": v["name"], "kind": v["kind"], "registration": "B2 YYY", "disconnect_mot": True}
    assert auth_client.put(f"/api/vehicles/{v['id']}", json=body).status_code == 200
    assert auth_client.get(f"/api/vehicles/{v['id']}/mot").json["mot"] is None
    assert auth_client.get(f"/api/vehicles/{v['id']}").json["mot_baseline"] is None
    # MOT-sourced mileage points are gone with the tests; the timeline is now empty.
    assert auth_client.get(f"/api/vehicles/{v['id']}/mileage").json == []


def test_update_without_disconnect_keeps_stored_data(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    v = mk_vehicle(auth_client, registration="A1 XYZ")
    auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")

    body = {"name": "Renamed", "kind": v["kind"], "registration": "A1 XYZ"}
    assert auth_client.put(f"/api/vehicles/{v['id']}", json=body).status_code == 200
    assert auth_client.get(f"/api/vehicles/{v['id']}/mot").json["mot"] is not None


def test_vehicle_detail_exposes_mot_baseline(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    v = mk_vehicle(auth_client, registration="A1 XYZ")  # no make/model/etc. set
    auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")

    detail = auth_client.get(f"/api/vehicles/{v['id']}").json
    b = detail["mot_baseline"]
    assert b["make"] == "VOLKSWAGEN"
    assert b["model"] == "PASSAT"
    assert b["year"] == 2003  # derived from manufactureDate (no manufactureYear)
    assert b["registration"] == "A1XYZ"
    assert b["colour"] == "Blue"
    assert b["fuel_type"] == "Diesel"
    assert b["engine_size"] == "1896"
    assert b["first_used_date"] == "2003-11-21"
    assert b["registration_date"] == "2003-11-21"
    # The user hasn't overridden anything, so the stored columns stay null
    assert detail["make"] is None
    assert detail["engine_size"] is None
    # ...and the backend resolves the effective value to the baseline, tagged as such.
    assert detail["effective"]["make"] == "VOLKSWAGEN"
    assert detail["effective"]["engine_size"] == "1896"
    assert detail["effective_source"]["make"] == "baseline"
    assert detail["effective_source"]["engine_size"] == "baseline"


def test_mot_baseline_prefers_manufacture_year(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: NEW_REG)
    v = mk_vehicle(auth_client, registration="A2 XYZ")
    auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    assert auth_client.get(f"/api/vehicles/{v['id']}").json["mot_baseline"]["year"] == 2024


def test_user_override_kept_alongside_mot_baseline(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    v = mk_vehicle(auth_client, registration="A1 XYZ", colour="Matte Black")
    auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    detail = auth_client.get(f"/api/vehicles/{v['id']}").json
    # Override and baseline coexist; the backend resolves precedence (override wins).
    assert detail["colour"] == "Matte Black"
    assert detail["mot_baseline"]["colour"] == "Blue"
    assert detail["effective"]["colour"] == "Matte Black"
    assert detail["effective_source"]["colour"] == "override"


def test_no_mot_baseline_without_snapshot(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client, registration="A1 XYZ")
    detail = auth_client.get(f"/api/vehicles/{v['id']}").json
    assert detail["mot_baseline"] is None
    # No override and no baseline: effective value is null, sourced from the (absent) baseline.
    assert detail["effective"]["make"] is None
    assert detail["effective_source"]["make"] == "baseline"
    # The registration the user set on the vehicle is still resolved as an override.
    assert detail["effective"]["registration"] == "A1 XYZ"
    assert detail["effective_source"]["registration"] == "override"


def test_vehicle_list_includes_mot_baseline(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    v = mk_vehicle(auth_client, registration="A1 XYZ")
    auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    row = next(x for x in auth_client.get("/api/vehicles").json if x["id"] == v["id"])
    assert row["mot_baseline"]["make"] == "VOLKSWAGEN"
    assert row["effective"]["make"] == "VOLKSWAGEN"
    assert row["effective_source"]["make"] == "baseline"


# ── admin DVSA vehicles list ────────────────────────────────────────────────────

def _seed_dvsa(garage_id: int, count: int) -> list[int]:
    """Create `count` vehicles each with a stored DVSA snapshot; return vehicle ids."""
    from torqued.db import get_db
    from torqued.repositories.mot_repository import MotRepository
    from torqued.repositories.vehicle_repository import VehicleRepository

    ids: list[int] = []
    with get_db() as db:
        vehicles = VehicleRepository(db)
        snapshots = MotRepository(db)
        for i in range(count):
            v = vehicles.create(garage_id, {"name": f"Car {i}"})
            snapshots.replace_for_vehicle(v["id"], {**SAMPLE, "registration": f"REG{i:03d}"})
            ids.append(v["id"])
    return ids


def test_dvsa_vehicles_requires_auth(client: FlaskClient) -> None:
    assert client.get("/api/dvsa-vehicles").status_code == 401


def test_dvsa_vehicles_requires_admin(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/dvsa-vehicles").status_code == 403


def test_dvsa_vehicles_ordered_by_fetched_at(
    admin_client: FlaskClient, garage: dict[str, Any]
) -> None:
    from torqued.db import execute_sql, get_db

    ids = _seed_dvsa(garage["id"], 3)
    with get_db() as db:
        for vid, ts in zip(
            ids, ["2024-01-01 00:00:00", "2024-03-01 00:00:00", "2024-02-01 00:00:00"]
        ):
            execute_sql(db, "UPDATE dvsa_vehicles SET fetched_at=? WHERE vehicle_id=?", (ts, vid))

    body = admin_client.get("/api/dvsa-vehicles").json
    assert body["total"] == 3
    assert body["pages"] == 1
    assert [i["fetched_at"] for i in body["items"]] == [
        "2024-03-01 00:00:00",
        "2024-02-01 00:00:00",
        "2024-01-01 00:00:00",
    ]
    assert body["items"][0]["make"] == "VOLKSWAGEN"
    assert body["items"][0]["vehicle_id"] is not None


def test_dvsa_vehicles_pagination(
    admin_client: FlaskClient, garage: dict[str, Any]
) -> None:
    _seed_dvsa(garage["id"], 26)

    page1 = admin_client.get("/api/dvsa-vehicles").json
    assert page1["total"] == 26
    assert page1["page"] == 1
    assert page1["per_page"] == 25
    assert page1["pages"] == 2
    assert len(page1["items"]) == 25

    page2 = admin_client.get("/api/dvsa-vehicles?page=2").json
    assert page2["page"] == 2
    assert len(page2["items"]) == 1


def test_dvsa_record_retained_after_vehicle_delete(
    admin_client: FlaskClient, garage: dict[str, Any]
) -> None:
    from torqued.db import get_db
    from torqued.repositories.mot_repository import MotRepository
    from torqued.repositories.vehicle_repository import VehicleRepository

    with get_db() as db:
        v = VehicleRepository(db).create(garage["id"], {"name": "Doomed"})
        MotRepository(db).replace_for_vehicle(v["id"], {**SAMPLE, "registration": "OLD123"})

    # Deleting the vehicle detaches (does not delete) its DVSA record.
    with get_db() as db:
        assert VehicleRepository(db).delete(v["id"]) is True

    items = admin_client.get("/api/dvsa-vehicles").json["items"]
    detached = [i for i in items if i["registration"] == "OLD123"]
    assert len(detached) == 1
    assert detached[0]["vehicle_id"] is None


# ── DVSA relink on create / edit ────────────────────────────────────────────────

def test_create_relinks_detached_dvsa_record(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    from sqlalchemy import select

    from torqued.db import get_db
    from torqued.models import DvsaVehicle

    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    old = mk_vehicle(auth_client, registration="A1 XYZ")
    auth_client.post(f"/api/vehicles/{old['id']}/mot/refresh")
    assert auth_client.delete(f"/api/vehicles/{old['id']}").status_code == 204

    # A new vehicle on the same plate adopts the detached snapshot.
    new = mk_vehicle(auth_client, registration="A1 XYZ")
    mot_data = auth_client.get(f"/api/vehicles/{new['id']}/mot").json["mot"]
    assert mot_data is not None
    assert mot_data["registration"] == "A1XYZ"
    # The cascade-deleted tests were rebuilt from raw_json, newest first.
    assert [t["mot_test_number"] for t in mot_data["tests"]] == ["1234", "1233", "1232"]

    # The detached row was reused (not duplicated) and now points at the new vehicle.
    with get_db() as db:
        linked = db.scalars(
            select(DvsaVehicle.vehicle_id).where(DvsaVehicle.registration == "A1XYZ")
        ).all()
    assert linked == [new["id"]]


def test_relink_normalises_registration(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    old = mk_vehicle(auth_client, registration="A1 XYZ")
    auth_client.post(f"/api/vehicles/{old['id']}/mot/refresh")
    auth_client.delete(f"/api/vehicles/{old['id']}")

    # A differently cased/spaced plate still matches the stored canonical "A1XYZ".
    new = mk_vehicle(auth_client, registration="a1 xyz")
    mot_data = auth_client.get(f"/api/vehicles/{new['id']}/mot").json["mot"]
    assert mot_data is not None
    assert [t["mot_test_number"] for t in mot_data["tests"]] == ["1234", "1233", "1232"]


def test_create_no_detached_record_is_noop(auth_client: FlaskClient) -> None:
    from torqued.db import get_db
    from torqued.repositories.mot_repository import MotRepository

    # A never-seen plate has nothing to relink.
    v = mk_vehicle(auth_client, registration="ZZ99 ZZZ")
    assert auth_client.get(f"/api/vehicles/{v['id']}/mot").json["mot"] is None

    # A blank registration short-circuits before the lookup.
    with get_db() as db:
        assert MotRepository(db).relink_detached(v["id"], "   ") is False


def test_relink_skips_live_record_of_another_vehicle(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    a = mk_vehicle(auth_client, registration="A1 XYZ")
    auth_client.post(f"/api/vehicles/{a['id']}/mot/refresh")

    # B takes the same plate while A is still live — A's record must not move to B.
    b = mk_vehicle(auth_client, registration="A1 XYZ")
    assert auth_client.get(f"/api/vehicles/{b['id']}/mot").json["mot"] is None
    assert auth_client.get(f"/api/vehicles/{a['id']}/mot").json["mot"] is not None


def test_edit_registration_relinks_detached(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    old = mk_vehicle(auth_client, registration="A1 XYZ")
    auth_client.post(f"/api/vehicles/{old['id']}/mot/refresh")
    auth_client.delete(f"/api/vehicles/{old['id']}")  # detaches the A1XYZ snapshot

    v = mk_vehicle(auth_client, registration="A2 XYZ")  # no DVSA data for A2XYZ
    assert auth_client.get(f"/api/vehicles/{v['id']}/mot").json["mot"] is None

    # Changing the plate to the detached one re-attaches its snapshot.
    r = auth_client.put(
        f"/api/vehicles/{v['id']}",
        json={"name": v["name"], "kind": v["kind"], "registration": "A1 XYZ"},
    )
    assert r.status_code == 200
    mot_data = auth_client.get(f"/api/vehicles/{v['id']}/mot").json["mot"]
    assert mot_data is not None
    assert [t["mot_test_number"] for t in mot_data["tests"]] == ["1234", "1233", "1232"]


def test_edit_skips_relink_when_live_record_exists(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    old = mk_vehicle(auth_client, registration="A1 XYZ")
    auth_client.post(f"/api/vehicles/{old['id']}/mot/refresh")
    auth_client.delete(f"/api/vehicles/{old['id']}")  # leaves a detached A1XYZ record

    # A vehicle that already has its own live DVSA record (A2XYZ)...
    v = mk_vehicle(auth_client, registration="A2 XYZ")
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: NEW_REG)
    auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    # ...keeps it when its plate changes — the detached A1XYZ record is not adopted.
    auth_client.put(
        f"/api/vehicles/{v['id']}",
        json={"name": v["name"], "kind": v["kind"], "registration": "A1 XYZ"},
    )
    mot_data = auth_client.get(f"/api/vehicles/{v['id']}/mot").json["mot"]
    assert mot_data is not None
    assert mot_data["registration"] == "A2XYZ"


def test_refresh_new_reg_vehicle(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: NEW_REG)
    v = mk_vehicle(auth_client, registration="A2 XYZ")
    r = auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    assert r.status_code == 200
    assert "odometer_logs_synced" not in r.json
    assert r.json["mot"]["mot_test_due_date"] == "2027-09-01"
    assert r.json["mot"]["manufacture_year"] == 2024
    assert r.json["mot"]["tests"] == []


# ── MOT reminders ───────────────────────────────────────────────────────────────

def _store_mot(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> dict[str, Any]:
    """Create a vehicle and persist the given DVSA payload against it."""
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: payload)
    v = mk_vehicle(auth_client, registration=payload["registration"])
    r = auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    assert r.status_code == 200, r.json
    return v


def _mot_reminders(auth_client: FlaskClient) -> list[dict[str, Any]]:
    return [r for r in auth_client.get("/api/reminders").json if r["type"] == "mot"]


def _passed(expiry: str | None) -> dict[str, Any]:
    return {"registration": "A1XYZ", "motTests": [
        {"completedDate": "2024-11-05T10:01:00.000Z", "testResult": "PASSED", "expiryDate": expiry},
    ]}


def test_mot_reminder_due_soon(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    expiry = (date.today() + timedelta(days=30)).isoformat()
    v = _store_mot(auth_client, monkeypatch, _passed(expiry))
    [rem] = _mot_reminders(auth_client)
    assert rem["status"] == "due_soon"
    assert rem["category"] == "MOT"
    assert rem["next_due_date"] == expiry
    assert rem["vehicle_id"] == v["id"]
    # The same reminder is embedded in the vehicle detail payload
    detail = auth_client.get(f"/api/vehicles/{v['id']}").json
    assert [r["status"] for r in detail["reminders"] if r["type"] == "mot"] == ["due_soon"]


def test_mot_reminder_overdue(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    expiry = (date.today() - timedelta(days=10)).isoformat()
    _store_mot(auth_client, monkeypatch, _passed(expiry))
    [rem] = _mot_reminders(auth_client)
    assert rem["status"] == "overdue"


def test_mot_reminder_outside_window_hidden(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    expiry = (date.today() + timedelta(days=120)).isoformat()
    _store_mot(auth_client, monkeypatch, _passed(expiry))
    assert _mot_reminders(auth_client) == []


def test_mot_reminder_falls_back_to_due_date(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    # Latest test failed (no expiry); the vehicle-level next-due date drives the reminder.
    due = (date.today() + timedelta(days=20)).isoformat()
    _store_mot(auth_client, monkeypatch, {
        "registration": "A1XYZ", "motTestDueDate": due, "motTests": [
            {"completedDate": "2024-11-05T10:01:00.000Z",
             "testResult": "FAILED", "expiryDate": None},
        ],
    })
    [rem] = _mot_reminders(auth_client)
    assert rem["status"] == "due_soon"
    assert rem["next_due_date"] == due


def test_mot_reminder_without_any_date_hidden(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    # A snapshot with no expiry and no due date has nothing to remind about.
    _store_mot(auth_client, monkeypatch, {"registration": "A1XYZ", "motTests": []})
    assert _mot_reminders(auth_client) == []


def test_mot_reminder_excludes_archived_vehicle(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    expiry = (date.today() + timedelta(days=30)).isoformat()
    v = _store_mot(auth_client, monkeypatch, _passed(expiry))
    auth_client.put(f"/api/vehicles/{v['id']}", json={"name": v["name"], "archived": True})
    assert _mot_reminders(auth_client) == []


def test_mot_reminders_empty_garages() -> None:
    from torqued.db import get_db
    from torqued.repositories.mot_repository import MotRepository

    with get_db() as db:
        assert MotRepository(db).reminders([]) == []


# ── effective MOT expiry (resolved server-side, not in the frontend) ────────────

def test_expiry_status_branches() -> None:
    from torqued.db import get_db
    from torqued.repositories.mot_repository import MOT_DUE_SOON_DAYS, MotRepository

    today = date(2026, 6, 24)
    with get_db() as db:
        repo = MotRepository(db)
        # No date anywhere → nothing to show.
        assert repo.expiry_status({"tests": []}, today=today) is None
        # Latest test already lapsed → expired.
        past = repo.expiry_status({"tests": [{"expiry_date": "2025-01-01"}]}, today=today)
        assert past == {"expiry_date": "2025-01-01", "status": "expired"}
        # Within the due-soon window → due_soon.
        soon = (today + timedelta(days=MOT_DUE_SOON_DAYS - 1)).isoformat()
        assert repo.expiry_status({"tests": [{"expiry_date": soon}]}, today=today)["status"] == (
            "due_soon"
        )
        # Comfortably in the future → ok.
        far = (today + timedelta(days=MOT_DUE_SOON_DAYS + 30)).isoformat()
        assert repo.expiry_status({"tests": [{"expiry_date": far}]}, today=today)["status"] == "ok"
        # No test expiry → falls back to the vehicle-level due date.
        fallback = repo.expiry_status(
            {"tests": [{"expiry_date": None}], "mot_test_due_date": far}, today=today
        )
        assert fallback == {"expiry_date": far, "status": "ok"}
