"""Tests for the DVSA MOT history integration: client, storage, and routes."""
import json
import urllib.error
from typing import Any

import pytest
from flask.testing import FlaskClient

from tests.test_vehicles import mk_vehicle
from torqued import mot

SAMPLE: dict[str, Any] = {
    "registration": "LR53UHD",
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
    "registration": "WA64XPW",
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
    assert mot.normalise_registration("lr53 uhd") == "LR53UHD"


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
    assert mot.fetch_vehicle("lr53 uhd")["registration"] == "LR53UHD"
    assert calls == ["https://login.example/token", mot.API_BASE + "LR53UHD"]
    # The token is cached: a second fetch skips the token endpoint
    mot.fetch_vehicle("LR53UHD")
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
        mot.fetch_vehicle("LR53UHD")
    assert e.value.status == 502


def test_fetch_vehicle_unreachable(monkeypatch: pytest.MonkeyPatch, mot_env: None) -> None:
    mot._token_cache.update({"token": "tok", "expires": 9e12})

    def fake_urlopen(req: Any, timeout: int = 0) -> FakeResponse:
        raise OSError("no route to host")

    monkeypatch.setattr(mot.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(mot.MotError) as e:
        mot.fetch_vehicle("LR53UHD")
    assert e.value.status == 502


def test_token_auth_failure(monkeypatch: pytest.MonkeyPatch, mot_env: None) -> None:
    def fake_urlopen(req: Any, timeout: int = 0) -> FakeResponse:
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", None, None)  # type: ignore[arg-type]

    monkeypatch.setattr(mot.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(mot.MotError, match="authentication failed"):
        mot.fetch_vehicle("LR53UHD")


def test_token_endpoint_unreachable(monkeypatch: pytest.MonkeyPatch, mot_env: None) -> None:
    def fake_urlopen(req: Any, timeout: int = 0) -> FakeResponse:
        raise OSError("timed out")

    monkeypatch.setattr(mot.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(mot.MotError, match="token endpoint"):
        mot.fetch_vehicle("LR53UHD")


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
    assert client.get("/api/mot/lookup/LR53UHD").status_code == 401


def test_lookup_unconfigured(auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    for v in ("MOT_CLIENT_ID", "MOT_CLIENT_SECRET", "MOT_TOKEN_URL", "MOT_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    assert auth_client.get("/api/mot/lookup/LR53UHD").status_code == 503


def test_lookup_success(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    r = auth_client.get("/api/mot/lookup/LR53%20UHD")
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
    veh = mk_vehicle(auth_client, registration="LR53 UHD")
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
    v = mk_vehicle(auth_client, registration="LR53 UHD")
    r = auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    assert r.status_code == 503


def test_refresh_relays_dvsa_error(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    def boom(reg: str) -> dict[str, Any]:
        raise mot.MotError("No MOT record found for registration LR53UHD", 404)

    monkeypatch.setattr(mot, "fetch_vehicle", boom)
    v = mk_vehicle(auth_client, registration="LR53 UHD")
    r = auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    assert r.status_code == 404
    assert "No MOT record" in r.json["error"]


def test_refresh_stores_and_syncs(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    v = mk_vehicle(auth_client, registration="LR53 UHD", odometer_unit="mi")
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
    assert m["raw"]["registration"] == "LR53UHD"
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
    assert g.json["mot"]["registration"] == "LR53UHD"


def test_vehicle_detail_exposes_mot_baseline(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    v = mk_vehicle(auth_client, registration="LR53 UHD")  # no make/model/etc. set
    auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")

    detail = auth_client.get(f"/api/vehicles/{v['id']}").json
    b = detail["mot_baseline"]
    assert b["make"] == "VOLKSWAGEN"
    assert b["model"] == "PASSAT"
    assert b["year"] == 2003  # derived from manufactureDate (no manufactureYear)
    assert b["registration"] == "LR53UHD"
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
    v = mk_vehicle(auth_client, registration="WA64 XPW")
    auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    assert auth_client.get(f"/api/vehicles/{v['id']}").json["mot_baseline"]["year"] == 2024


def test_user_override_kept_alongside_mot_baseline(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    v = mk_vehicle(auth_client, registration="LR53 UHD", colour="Matte Black")
    auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    detail = auth_client.get(f"/api/vehicles/{v['id']}").json
    # Override and baseline coexist; the frontend resolves precedence
    assert detail["colour"] == "Matte Black"
    assert detail["mot_baseline"]["colour"] == "Blue"


def test_no_mot_baseline_without_snapshot(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client, registration="LR53 UHD")
    assert auth_client.get(f"/api/vehicles/{v['id']}").json["mot_baseline"] is None


def test_vehicle_list_includes_mot_baseline(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    v = mk_vehicle(auth_client, registration="LR53 UHD")
    auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    row = next(x for x in auth_client.get("/api/vehicles").json if x["id"] == v["id"])
    assert row["mot_baseline"]["make"] == "VOLKSWAGEN"


def test_refresh_new_reg_vehicle(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, mot_env: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: NEW_REG)
    v = mk_vehicle(auth_client, registration="WA64 XPW")
    r = auth_client.post(f"/api/vehicles/{v['id']}/mot/refresh")
    assert r.status_code == 200
    assert "odometer_logs_synced" not in r.json
    assert r.json["mot"]["mot_test_due_date"] == "2027-09-01"
    assert r.json["mot"]["manufacture_year"] == 2024
    assert r.json["mot"]["tests"] == []
