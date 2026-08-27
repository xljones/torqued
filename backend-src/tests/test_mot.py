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


def test_effective_endpoint(mot_env: None) -> None:
    ep = mot.effective_endpoint()
    assert ep["configured"] is True
    assert ep["url"] == mot.API_BASE
    # No secrets or the token URL leak into the admin-facing payload.
    assert set(ep) == {"configured", "url"}


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
    # Override and baseline coexist; the frontend resolves precedence
    assert detail["colour"] == "Matte Black"
    assert detail["mot_baseline"]["colour"] == "Blue"


def test_no_mot_baseline_without_snapshot(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client, registration="A1 XYZ")
    assert auth_client.get(f"/api/vehicles/{v['id']}").json["mot_baseline"] is None


def test_vehicle_list_includes_mot_baseline(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    v = mk_vehicle(auth_client, registration="A1 XYZ")
    auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    row = next(x for x in auth_client.get("/api/vehicles").json if x["id"] == v["id"])
    assert row["mot_baseline"]["make"] == "VOLKSWAGEN"


# ── DVSA record retention & standalone lookups ──────────────────────────────────
# (The admin records *list* / *records* endpoints — now unified with tax — live in
# test_records.py; these cover DVSA-specific storage the MotRepository owns.)

def _lookup_twice(garage_id: int, registration: str) -> int:
    """Refresh one vehicle twice → two dated lookup records for one plate."""
    from torqued.db import get_db
    from torqued.repositories.mot_repository import MotRepository
    from torqued.repositories.vehicle_repository import VehicleRepository

    with get_db() as db:
        v = VehicleRepository(db).create(garage_id, {"name": "Car"})
        MotRepository(db).replace_for_vehicle(v["id"], {**SAMPLE, "registration": registration})
    with get_db() as db:
        MotRepository(db).replace_for_vehicle(v["id"], {**SAMPLE, "registration": registration})
    return int(v["id"])


def test_refresh_keeps_previous_lookup_as_history(
    garage: dict[str, Any]
) -> None:
    """A refresh retains the prior lookup (detached), not deletes it."""
    from torqued.db import get_db
    from torqued.repositories.mot_repository import MotRepository

    from sqlalchemy import select

    from torqued.models import DvsaVehicle

    vehicle_id = _lookup_twice(garage["id"], "A1XYZ")
    with get_db() as db:
        rows = db.scalars(select(DvsaVehicle).order_by(DvsaVehicle.id)).all()
        assert len(rows) == 2  # both lookups kept
        assert [r.vehicle_id for r in rows] == [None, vehicle_id]  # older detached, newer live
        # The vehicle still resolves to exactly its current (live) snapshot.
        assert MotRepository(db).get_for_vehicle(vehicle_id) is not None


def test_create_dvsa_lookup_requires_auth(client: FlaskClient) -> None:
    assert client.post("/api/dvsa-vehicles", json={"registration": "A1XYZ"}).status_code == 401


def test_create_dvsa_lookup_requires_admin(auth_client: FlaskClient) -> None:
    assert auth_client.post("/api/dvsa-vehicles", json={"registration": "A1XYZ"}).status_code == 403


def test_create_dvsa_lookup_requires_registration(admin_client: FlaskClient) -> None:
    assert admin_client.post("/api/dvsa-vehicles", json={}).status_code == 400


def test_create_dvsa_lookup_unconfigured(
    admin_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mot, "is_configured", lambda: False)
    r = admin_client.post("/api/dvsa-vehicles", json={"registration": "A1XYZ"})
    assert r.status_code == 503


def test_create_dvsa_lookup_relays_dvsa_error(
    admin_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    def boom(reg: str) -> dict[str, Any]:
        raise mot.MotError("No MOT record found", 404)

    monkeypatch.setattr(mot, "fetch_vehicle", boom)
    r = admin_client.post("/api/dvsa-vehicles", json={"registration": "A1XYZ"})
    assert r.status_code == 404
    assert "No MOT record" in r.json["error"]


def test_create_dvsa_lookup_persists_detached(
    admin_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    r = admin_client.post("/api/dvsa-vehicles", json={"registration": "A1 XYZ"})
    assert r.status_code == 201
    assert r.json["make"] == "VOLKSWAGEN"

    items = admin_client.get("/api/vehicle-records").json["items"]
    item = next(i for i in items if (i["registration"] or "").replace(" ", "").upper() == "A1XYZ")
    assert item["vehicle_id"] is None  # not assigned to any garage vehicle
    assert item["record_count"] == 1


def test_standalone_lookup_links_when_vehicle_added_later(
    auth_client: FlaskClient, garage: dict[str, Any]
) -> None:
    from torqued.db import get_db
    from torqued.repositories.mot_repository import MotRepository

    # A standalone (unassigned) lookup persisted earlier via the admin page.
    with get_db() as db:
        MotRepository(db).store_detached_lookup({**SAMPLE, "registration": "A1XYZ"})

    # Adding a vehicle on that plate ties the old record to it, rebuilding its tests.
    v = mk_vehicle(auth_client, registration="A1 XYZ")
    mot_data = auth_client.get(f"/api/vehicles/{v['id']}/mot").json["mot"]
    assert mot_data is not None
    assert mot_data["registration"] == "A1XYZ"
    assert [t["mot_test_number"] for t in mot_data["tests"]] == ["1234", "1233", "1232"]


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


def test_create_reties_all_historic_records(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    from torqued.db import get_db
    from torqued.repositories.records_repository import RecordsRepository

    # A vehicle refreshed twice keeps both lookups; deleting it detaches them.
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    old = mk_vehicle(auth_client, registration="A1 XYZ")
    auth_client.post(f"/api/vehicles/{old['id']}/mot/refresh")
    auth_client.post(f"/api/vehicles/{old['id']}/mot/refresh")
    auth_client.delete(f"/api/vehicles/{old['id']}")

    # Adding a new vehicle on that plate reties the history: the newest lookup becomes
    # the live snapshot and every historic lookup groups under the new vehicle.
    new = mk_vehicle(auth_client, registration="A1 XYZ")
    assert auth_client.get(f"/api/vehicles/{new['id']}/mot").json["mot"] is not None

    with get_db() as db:
        item = next(
            i
            for i in RecordsRepository(db).list_all()["items"]
            if (i["registration"] or "").replace(" ", "").upper() == "A1XYZ"
        )
    assert item["record_count"] == 2
    assert item["vehicle_id"] == new["id"]


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


def _store_ves_mot(vehicle_id: int, expiry: str | None) -> None:
    """Persist a DVLA VES record (with a MOT expiry) against a vehicle."""
    from torqued.db import get_db
    from torqued.repositories.ves_repository import VesRepository

    with get_db() as db:
        VesRepository(db).replace_for_vehicle(
            vehicle_id,
            {"registration": "A1XYZ", "mot_status": "valid MOT", "mot_expiry_date": expiry},
        )


def test_mot_reminder_ves_supplements_stale_dvsa(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    # DVSA history is stale (expiry in the past → would be overdue), but the DVLA VES status
    # shows a fresh future expiry, so the false 'overdue' reminder is suppressed. This is the
    # YT12OPZ (SORN, DVSA-lagging) case.
    past = (date.today() - timedelta(days=10)).isoformat()
    future = (date.today() + timedelta(days=300)).isoformat()
    v = _store_mot(auth_client, monkeypatch, _passed(past))
    _store_ves_mot(v["id"], future)
    assert _mot_reminders(auth_client) == []


def test_mot_reminder_ves_earlier_does_not_override_valid_dvsa(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    # A stale/earlier VES expiry never forces a false 'overdue' when DVSA has a later pass:
    # the governing date is the later of the two, and only one 'mot' reminder is ever emitted.
    dvsa_future = (date.today() + timedelta(days=200)).isoformat()
    ves_past = (date.today() - timedelta(days=10)).isoformat()
    v = _store_mot(auth_client, monkeypatch, _passed(dvsa_future))
    _store_ves_mot(v["id"], ves_past)
    assert _mot_reminders(auth_client) == []  # 200 days out, well outside the window


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


def test_mot_reminders_standalone(garage: dict) -> None:
    """Called outside the orchestrator, the repository resolves the windows itself."""
    from torqued.db import get_db
    from torqued.repositories.mot_repository import MotRepository

    with get_db() as db:
        assert MotRepository(db).reminders([]) == []
        assert MotRepository(db).reminders([garage["id"]]) == []


# ── MOT summaries (vehicle list cards) ──────────────────────────────────────────

def test_vehicle_list_includes_mot_summary(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    v = mk_vehicle(auth_client, registration="A1 XYZ")
    auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    row = next(x for x in auth_client.get("/api/vehicles").json if x["id"] == v["id"])
    # Latest test passed; its expiry drives the summary.
    assert row["mot_summary"] == {"expiry": "2025-11-04", "failed": False}


def test_mot_summary_flags_a_failed_latest_test(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    payload: dict[str, Any] = {"registration": "A9XYZ", "motTests": [
        {"completedDate": "2025-01-02T00:00:00.000Z", "testResult": "FAILED", "expiryDate": None},
    ]}
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: payload)
    v = mk_vehicle(auth_client, registration="A9 XYZ")
    auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    row = next(x for x in auth_client.get("/api/vehicles").json if x["id"] == v["id"])
    assert row["mot_summary"] == {"expiry": None, "failed": True}


def test_mot_summary_falls_back_to_due_date(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    # NEW_REG has a vehicle-level due date but no tests.
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: NEW_REG)
    v = mk_vehicle(auth_client, registration="A2 XYZ")
    auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    row = next(x for x in auth_client.get("/api/vehicles").json if x["id"] == v["id"])
    assert row["mot_summary"] == {"expiry": "2027-09-01", "failed": False}


def test_mot_summary_consolidates_latest_of_both_sources(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    # DVSA history lapsed in 2025, but the DVLA VES status is valid into 2027 → the list pill
    # shows the later (VES) date, not a false "expired". Mirrors the detail card.
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: _passed("2025-05-09"))
    v = mk_vehicle(auth_client, registration="A5 XYZ")
    auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    _store_ves_mot(v["id"], "2027-08-20")
    row = next(x for x in auth_client.get("/api/vehicles").json if x["id"] == v["id"])
    assert row["mot_summary"] == {"expiry": "2027-08-20", "failed": False}


def test_mot_summary_ves_clears_a_failed_dvsa_latest(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    # A fresh VES pass means the stale DVSA "failed" latest test no longer governs.
    payload: dict[str, Any] = {"registration": "A9XYZ", "motTests": [
        {"completedDate": "2025-01-02T00:00:00.000Z", "testResult": "FAILED", "expiryDate": None},
    ]}
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: payload)
    v = mk_vehicle(auth_client, registration="A8 XYZ")
    auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    _store_ves_mot(v["id"], "2027-08-20")
    row = next(x for x in auth_client.get("/api/vehicles").json if x["id"] == v["id"])
    assert row["mot_summary"] == {"expiry": "2027-08-20", "failed": False}


def test_mot_summary_from_ves_only(auth_client: FlaskClient) -> None:
    # A vehicle with only a DVLA VES record (no DVSA snapshot) still gets a MOT pill.
    v = mk_vehicle(auth_client, registration="A7 XYZ")
    _store_ves_mot(v["id"], "2027-08-20")
    row = next(x for x in auth_client.get("/api/vehicles").json if x["id"] == v["id"])
    assert row["mot_summary"] == {"expiry": "2027-08-20", "failed": False}


def test_mot_summaries_empty() -> None:
    from torqued.db import get_db
    from torqued.repositories.vehicle_repository import VehicleRepository

    with get_db() as db:
        assert VehicleRepository(db).mot_summaries([]) == {}
