"""Tests for the DVLA road-tax (VES) integration: client, storage, routes, reminders."""
import json
import urllib.error
from datetime import date
from typing import Any

import pytest
from flask.testing import FlaskClient

from tests.test_vehicles import mk_vehicle
from torqued import ves

SAMPLE: dict[str, Any] = {
    "registrationNumber": "LR53UHD",
    "taxStatus": "Taxed",
    "taxDueDate": "2026-09-01",
    "motStatus": "Valid",
    "motExpiryDate": "2026-08-15",
    "make": "VOLKSWAGEN",
    "colour": "Blue",
    "fuelType": "Diesel",
    "yearOfManufacture": 2003,
    "engineCapacity": 1896,
    "co2Emissions": 155,
    "markedForExport": False,
    "typeApproval": "M1",
    "wheelplan": "2 AXLE RIGID BODY",
    "revenueWeight": 1850,
    "realDrivingEmissions": "1",
    "euroStatus": "EURO 4",
    "dateOfLastV5CIssued": "2021-03-05",
    "monthOfFirstRegistration": "2003-11",
    "monthOfFirstDvlaRegistration": "2003-11",
    "artEndDate": "2027-09-01",
    "automatedVehicle": False,
}


@pytest.fixture
def ves_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VES_API_KEY", "key")


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

def test_is_configured(monkeypatch: pytest.MonkeyPatch, ves_env: None) -> None:
    assert ves.is_configured() is True
    monkeypatch.delenv("VES_API_KEY")
    assert ves.is_configured() is False


def test_fetch_vehicle_success(monkeypatch: pytest.MonkeyPatch, ves_env: None) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req: Any, timeout: int = 0) -> FakeResponse:
        captured["url"] = req.full_url
        captured["key"] = req.headers["X-api-key"]
        captured["body"] = json.loads(req.data.decode())
        return FakeResponse(SAMPLE)

    monkeypatch.setattr(ves.urllib.request, "urlopen", fake_urlopen)
    assert ves.fetch_vehicle("lr53 uhd")["taxStatus"] == "Taxed"
    assert captured["url"] == ves.DEFAULT_API_URL
    assert captured["key"] == "key"
    assert captured["body"] == {"registrationNumber": "LR53UHD"}


def test_fetch_vehicle_uses_custom_url(monkeypatch: pytest.MonkeyPatch, ves_env: None) -> None:
    monkeypatch.setenv("VES_API_URL", "https://uat.example/ves")
    seen: dict[str, str] = {}

    def fake_urlopen(req: Any, timeout: int = 0) -> FakeResponse:
        seen["url"] = req.full_url
        return FakeResponse(SAMPLE)

    monkeypatch.setattr(ves.urllib.request, "urlopen", fake_urlopen)
    ves.fetch_vehicle("LR53UHD")
    assert seen["url"] == "https://uat.example/ves"


def test_fetch_vehicle_not_found(monkeypatch: pytest.MonkeyPatch, ves_env: None) -> None:
    def fake_urlopen(req: Any, timeout: int = 0) -> FakeResponse:
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", None, None)  # type: ignore[arg-type]

    monkeypatch.setattr(ves.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(ves.VesError) as e:
        ves.fetch_vehicle("XX99XXX")
    assert e.value.status == 404


def test_fetch_vehicle_bad_request(monkeypatch: pytest.MonkeyPatch, ves_env: None) -> None:
    def fake_urlopen(req: Any, timeout: int = 0) -> FakeResponse:
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", None, None)  # type: ignore[arg-type]

    monkeypatch.setattr(ves.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(ves.VesError) as e:
        ves.fetch_vehicle("!!!")
    assert e.value.status == 400


def test_fetch_vehicle_api_error(monkeypatch: pytest.MonkeyPatch, ves_env: None) -> None:
    def fake_urlopen(req: Any, timeout: int = 0) -> FakeResponse:
        raise urllib.error.HTTPError(req.full_url, 500, "Server Error", None, None)  # type: ignore[arg-type]

    monkeypatch.setattr(ves.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(ves.VesError) as e:
        ves.fetch_vehicle("LR53UHD")
    assert e.value.status == 502


def test_fetch_vehicle_unreachable(monkeypatch: pytest.MonkeyPatch, ves_env: None) -> None:
    def fake_urlopen(req: Any, timeout: int = 0) -> FakeResponse:
        raise OSError("no route to host")

    monkeypatch.setattr(ves.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(ves.VesError) as e:
        ves.fetch_vehicle("LR53UHD")
    assert e.value.status == 502


# ── routes ────────────────────────────────────────────────────────────────────

def test_get_tax_requires_auth(client: FlaskClient) -> None:
    assert client.get("/api/vehicles/1/tax").status_code == 401


def test_tax_status(auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VES_API_KEY", raising=False)
    assert auth_client.get("/api/tax/status").json == {"configured": False}
    monkeypatch.setenv("VES_API_KEY", "k")
    assert auth_client.get("/api/tax/status").json == {"configured": True}


def test_get_tax_vehicle_404(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/vehicles/999/tax").status_code == 404


def test_get_tax_empty(auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VES_API_KEY", raising=False)
    veh = mk_vehicle(auth_client, registration="LR53 UHD")
    r = auth_client.get(f"/api/vehicles/{veh['id']}/tax")
    assert r.status_code == 200
    assert r.json == {"configured": False, "tax": None}


def test_refresh_vehicle_404(auth_client: FlaskClient) -> None:
    assert auth_client.post("/api/vehicles/999/tax/refresh").status_code == 404


def test_refresh_readonly_403(readonly_client: FlaskClient, garage: dict[str, Any]) -> None:
    from torqued.db import get_db
    from torqued.repositories.vehicle_repository import VehicleRepository

    with get_db() as db:
        v = VehicleRepository(db).create(garage["id"], {"name": "Shared bike"})
    assert readonly_client.post(f"/api/vehicles/{v['id']}/tax/refresh").status_code == 403


def test_refresh_without_registration(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    r = auth_client.post(f"/api/vehicles/{v['id']}/tax/refresh")
    assert r.status_code == 400
    assert "registration" in r.json["error"]


def test_refresh_unconfigured(auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VES_API_KEY", raising=False)
    v = mk_vehicle(auth_client, registration="LR53 UHD")
    assert auth_client.post(f"/api/vehicles/{v['id']}/tax/refresh").status_code == 503


def test_refresh_relays_dvla_error(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, ves_env: None
) -> None:
    def boom(reg: str) -> dict[str, Any]:
        raise ves.VesError("No DVLA record found", 404)

    monkeypatch.setattr(ves, "fetch_vehicle", boom)
    v = mk_vehicle(auth_client, registration="LR53 UHD")
    r = auth_client.post(f"/api/vehicles/{v['id']}/tax/refresh")
    assert r.status_code == 404
    assert "No DVLA record" in r.json["error"]


def test_refresh_stores_and_reads_back(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, ves_env: None
) -> None:
    monkeypatch.setattr(ves, "fetch_vehicle", lambda reg: SAMPLE)
    v = mk_vehicle(auth_client, registration="LR53 UHD")

    r = auth_client.post(f"/api/vehicles/{v['id']}/tax/refresh")
    assert r.status_code == 200
    tax = r.json["tax"]
    assert tax["tax_status"] == "Taxed"
    assert tax["tax_due_date"] == "2026-09-01"
    assert tax["mot_status"] == "Valid"
    # Every scalar field is promoted to a column, not just tax/MOT
    assert tax["make"] == "VOLKSWAGEN"
    assert tax["engine_capacity"] == 1896
    assert tax["co2_emissions"] == 155
    assert tax["euro_status"] == "EURO 4"
    assert tax["date_of_last_v5c_issued"] == "2021-03-05"
    assert tax["art_end_date"] == "2027-09-01"
    assert tax["marked_for_export"] == 0  # JSON false stored as 0
    # …and the full verbatim payload is still kept
    assert tax["raw"] == SAMPLE
    assert tax["raw"]["registrationNumber"] == "LR53UHD"

    # GET returns the stored snapshot; refresh is idempotent (replace-on-refresh)
    g = auth_client.get(f"/api/vehicles/{v['id']}/tax")
    assert g.json["configured"] is True
    assert g.json["tax"]["tax_due_date"] == "2026-09-01"
    auth_client.post(f"/api/vehicles/{v['id']}/tax/refresh")
    assert auth_client.get(f"/api/vehicles/{v['id']}/tax").json["tax"]["registration"] == "LR53UHD"


# ── reminders ───────────────────────────────────────────────────────────────--

def test_tax_reminders_no_garages(app: Any) -> None:
    from torqued.db import get_db
    from torqued.repositories.ves_repository import VesRepository

    with get_db() as db:
        assert VesRepository(db).tax_reminders([]) == []


def test_tax_reminders_statuses(auth_client: FlaskClient) -> None:
    from torqued.db import get_db
    from torqued.repositories.ves_repository import VesRepository

    over = mk_vehicle(auth_client, name="Overdue", registration="AA11AAA")
    soon = mk_vehicle(auth_client, name="Soon", registration="BB22BBB")
    up = mk_vehicle(auth_client, name="Upcoming", registration="CC33CCC")
    sorn = mk_vehicle(auth_client, name="Off road", registration="DD44DDD")
    gid = over["garage_id"]

    with get_db() as db:
        repo = VesRepository(db)
        repo.replace_for_vehicle(over["id"], {"registrationNumber": "AA11AAA", "taxDueDate": "2020-01-01"})
        repo.replace_for_vehicle(soon["id"], {"registrationNumber": "BB22BBB", "taxDueDate": "2020-01-20"})
        repo.replace_for_vehicle(up["id"], {"registrationNumber": "CC33CCC", "taxDueDate": "2020-06-01"})
        repo.replace_for_vehicle(sorn["id"], {"registrationNumber": "DD44DDD", "taxStatus": "SORN", "taxDueDate": None})
        rems = repo.tax_reminders([gid], today=date(2020, 1, 5))

    by_vehicle = {r["vehicle_id"]: r for r in rems}
    assert by_vehicle[over["id"]]["status"] == "overdue"
    assert by_vehicle[soon["id"]]["status"] == "due_soon"
    assert by_vehicle[up["id"]]["status"] == "upcoming"
    assert sorn["id"] not in by_vehicle  # no due date → no reminder

    r = by_vehicle[over["id"]]
    assert r["source"] == "tax"
    assert r["id"] == f"tax-{over['id']}"
    assert r["title"] == "Road tax"
    assert r["category"] is None
    assert r["next_due_km"] is None
    assert r["km_remaining"] is None


def test_reminders_merge_service_and_tax(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, ves_env: None
) -> None:
    payload = {"registrationNumber": "LR53UHD", "taxStatus": "Taxed", "taxDueDate": "2099-12-31"}
    monkeypatch.setattr(ves, "fetch_vehicle", lambda reg: payload)
    v = mk_vehicle(auth_client, registration="LR53 UHD")
    # An overdue service reminder
    auth_client.post(f"/api/vehicles/{v['id']}/services", json={
        "date": "2020-01-01", "title": "Oil change", "category": "Oil change",
        "next_due_date": "2020-06-01",
    })
    auth_client.post(f"/api/vehicles/{v['id']}/tax/refresh")

    rems = auth_client.get("/api/reminders").json
    # Overdue service sorts before the (far-future) upcoming tax reminder
    assert rems[0].get("source") is None
    assert rems[0]["status"] == "overdue"
    tax = next(r for r in rems if r.get("source") == "tax")
    assert tax["status"] == "upcoming"
    assert tax["next_due_date"] == "2099-12-31"
    assert tax["vehicle_id"] == v["id"]

    # The vehicle detail endpoint embeds the tax reminder too
    detail = auth_client.get(f"/api/vehicles/{v['id']}").json
    assert any(r.get("source") == "tax" for r in detail["reminders"])
