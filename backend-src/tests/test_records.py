"""Tests for the unified DVLA VES + DVSA records admin page.

Covers the ``/api/vehicle-records`` list and ``/records`` endpoints (RecordsRepository)
and the combined ``POST /api/vehicle-records`` lookup that fetches + persists both sources.
DVSA-only storage lives in test_mot.py, VES-only in test_ves.py.
"""
from typing import Any

import pytest
from flask.testing import FlaskClient

from tests.test_mot import SAMPLE
from torqued import mot, ves

TAX_PAYLOAD = {
    "registration": "A1XYZ",
    "tax_status": "Taxed",
    "tax_due_date": "2026-12-01",
    "mot_status": "Vehicle A1XYZ has a valid MOT certificate",
    "mot_expiry_date": "2027-06-11",
}


def _store_dvsa(garage_id: int, registration: str, name: str = "Car") -> int:
    from torqued.db import get_db
    from torqued.repositories.mot_repository import MotRepository
    from torqued.repositories.vehicle_repository import VehicleRepository

    with get_db() as db:
        v = VehicleRepository(db).create(garage_id, {"name": name})
        MotRepository(db).replace_for_vehicle(v["id"], {**SAMPLE, "registration": registration})
    return int(v["id"])


def _store_ves(garage_id: int, registration: str, name: str = "Car") -> int:
    from torqued.db import get_db
    from torqued.repositories.ves_repository import VesRepository
    from torqued.repositories.vehicle_repository import VehicleRepository

    with get_db() as db:
        v = VehicleRepository(db).create(garage_id, {"name": name})
        VesRepository(db).replace_for_vehicle(v["id"], {**TAX_PAYLOAD, "registration": registration})
    return int(v["id"])


def _detached(source: str, payload: dict[str, Any]) -> None:
    from torqued.db import get_db
    from torqued.repositories.mot_repository import MotRepository
    from torqued.repositories.ves_repository import VesRepository

    with get_db() as db:
        repo = MotRepository(db) if source == "dvsa" else VesRepository(db)
        repo.store_detached_lookup(payload)


# ── list endpoint: auth & shape ──────────────────────────────────────────────────

def test_records_requires_auth(client: FlaskClient) -> None:
    assert client.get("/api/vehicle-records").status_code == 401


def test_records_requires_admin(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/vehicle-records").status_code == 403


def test_records_empty(admin_client: FlaskClient) -> None:
    body = admin_client.get("/api/vehicle-records").json
    assert body == {
        "items": [], "total": 0, "total_records": 0, "total_dvsa": 0, "total_ves": 0,
        "page": 1, "per_page": 25, "pages": 0,
    }


# ── grouping across sources ──────────────────────────────────────────────────────

def test_records_group_dvsa_and_tax_of_one_plate(
    admin_client: FlaskClient, garage: dict[str, Any]
) -> None:
    # One vehicle with both a DVSA and a tax lookup for its plate.
    from torqued.db import get_db
    from torqued.repositories.ves_repository import VesRepository

    vid = _store_dvsa(garage["id"], "A1XYZ", name="Daily")
    with get_db() as db:
        VesRepository(db).replace_for_vehicle(vid, TAX_PAYLOAD)

    body = admin_client.get("/api/vehicle-records").json
    assert body["total"] == 1  # one vehicle
    assert body["total_records"] == 2  # a DVSA + a VES lookup
    assert body["total_dvsa"] == 1
    assert body["total_ves"] == 1
    item = body["items"][0]
    assert item["record_count"] == 2
    assert item["dvsa_count"] == 1
    assert item["ves_count"] == 1
    # Identity from the DVSA lookup, tax + MOT status from the VES lookup, both on one row.
    assert item["make"] == "VOLKSWAGEN"
    assert item["year"] == 2003
    assert item["tax_status"] == "Taxed"
    assert item["tax_due_date"] == "2026-12-01"
    assert item["mot_expiry_date"] == "2027-06-11"
    assert item["vehicle_id"] == vid
    assert item["vehicle_name"] == "Daily"
    assert item["garage_name"] == "Test Garage"


def test_records_separate_plates_are_separate_rows(
    admin_client: FlaskClient, garage: dict[str, Any]
) -> None:
    _store_dvsa(garage["id"], "AA11AAA")
    _store_ves(garage["id"], "BB22BBB")
    body = admin_client.get("/api/vehicle-records").json
    assert body["total"] == 2
    assert body["total_records"] == 2


def test_records_ordered_newest_first(
    admin_client: FlaskClient, garage: dict[str, Any]
) -> None:
    from torqued.db import execute_sql, get_db

    dv = _store_dvsa(garage["id"], "AA11AAA", name="Old")
    tv = _store_ves(garage["id"], "BB22BBB", name="New")
    with get_db() as db:
        execute_sql(db, "UPDATE dvsa_vehicles SET fetched_at=? WHERE vehicle_id=?",
                    ("2024-01-01 00:00:00", dv))
        execute_sql(db, "UPDATE vehicle_ves SET fetched_at=? WHERE vehicle_id=?",
                    ("2024-05-01 00:00:00", tv))

    items = admin_client.get("/api/vehicle-records").json["items"]
    assert [i["fetched_at"] for i in items] == ["2024-05-01 00:00:00", "2024-01-01 00:00:00"]


def test_records_pagination(admin_client: FlaskClient, garage: dict[str, Any]) -> None:
    for i in range(26):
        _store_dvsa(garage["id"], f"REG{i:03d}", name=f"Car {i}")
    page1 = admin_client.get("/api/vehicle-records").json
    assert page1["total"] == 26
    assert page1["pages"] == 2
    assert len(page1["items"]) == 25
    page2 = admin_client.get("/api/vehicle-records?page=2").json
    assert page2["page"] == 2
    assert len(page2["items"]) == 1


def test_records_year_derivation(admin_client: FlaskClient) -> None:
    _detached("dvsa", {"registration": "YEAR111", "manufactureYear": 2024})
    _detached("dvsa", {"registration": "DATE222", "firstUsedDate": "2015-06-01"})
    _detached("dvsa", {"registration": "NONE333"})
    years = {i["registration"]: i["year"] for i in admin_client.get("/api/vehicle-records").json["items"]}
    assert years["YEAR111"] == 2024
    assert years["DATE222"] == 2015
    assert years["NONE333"] is None


def test_records_link_falls_back_to_older_live_vehicle(
    admin_client: FlaskClient, garage: dict[str, Any]
) -> None:
    from torqued.db import get_db
    from torqued.repositories.mot_repository import MotRepository
    from torqued.repositories.vehicle_repository import VehicleRepository

    with get_db() as db:
        v1 = VehicleRepository(db).create(garage["id"], {"name": "First"})
        MotRepository(db).replace_for_vehicle(v1["id"], {**SAMPLE, "registration": "A1XYZ"})
    with get_db() as db:
        v2 = VehicleRepository(db).create(garage["id"], {"name": "Second"})
        MotRepository(db).replace_for_vehicle(v2["id"], {**SAMPLE, "registration": "A1XYZ"})
    with get_db() as db:
        VehicleRepository(db).delete(v2["id"])  # newest lookup detaches

    item = admin_client.get("/api/vehicle-records").json["items"][0]
    assert item["record_count"] == 2
    assert item["vehicle_id"] == v1["id"]


# ── records-for-plate endpoint ───────────────────────────────────────────────────

def test_records_for_requires_admin(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/vehicle-records/dvsa/1/records").status_code == 403


def test_records_for_unknown_source(admin_client: FlaskClient) -> None:
    assert admin_client.get("/api/vehicle-records/bogus/1/records").status_code == 404


def test_records_for_unknown_id(admin_client: FlaskClient) -> None:
    assert admin_client.get("/api/vehicle-records/dvsa/999/records").status_code == 404


def test_records_for_returns_both_sources_newest_first(
    admin_client: FlaskClient, garage: dict[str, Any]
) -> None:
    from torqued.db import execute_sql, get_db
    from torqued.repositories.ves_repository import VesRepository

    vid = _store_dvsa(garage["id"], "A1XYZ")
    with get_db() as db:
        VesRepository(db).replace_for_vehicle(vid, TAX_PAYLOAD)
        # Make the tax lookup the newer of the two.
        execute_sql(db, "UPDATE dvsa_vehicles SET fetched_at=? WHERE vehicle_id=?",
                    ("2024-01-01 00:00:00", vid))
        execute_sql(db, "UPDATE vehicle_ves SET fetched_at=? WHERE vehicle_id=?",
                    ("2024-05-01 00:00:00", vid))

    ref = admin_client.get("/api/vehicle-records").json["items"][0]["ref"]
    body = admin_client.get(f"/api/vehicle-records/{ref['source']}/{ref['id']}/records").json
    assert body["registration"] == "A1XYZ"
    assert [r["source"] for r in body["records"]] == ["ves", "dvsa"]
    # Each record carries its whole raw payload. The VES record exposes tax + MOT.
    ves_rec = body["records"][0]
    assert ves_rec["tax_status"] == "Taxed"
    assert ves_rec["mot_expiry_date"] == "2027-06-11"
    assert ves_rec["raw"]["tax_due_date"] == "2026-12-01"
    assert ves_rec["raw"]["mot_status"] == "Vehicle A1XYZ has a valid MOT certificate"
    dvsa_rec = body["records"][1]
    assert len(dvsa_rec["raw"]["motTests"]) == 3


def test_records_for_without_registration_returns_self(
    admin_client: FlaskClient
) -> None:
    _detached("dvsa", {k: v for k, v in SAMPLE.items() if k != "registration"})
    ref = admin_client.get("/api/vehicle-records").json["items"][0]["ref"]
    body = admin_client.get(f"/api/vehicle-records/{ref['source']}/{ref['id']}/records").json
    assert body["registration"] is None
    assert len(body["records"]) == 1
    assert body["records"][0]["raw"]["make"] == "VOLKSWAGEN"


# ── combined lookup (POST) ───────────────────────────────────────────────────────

@pytest.fixture
def both_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOT_CLIENT_ID", "cid")
    monkeypatch.setenv("MOT_CLIENT_SECRET", "secret")
    monkeypatch.setenv("MOT_TOKEN_URL", "https://login.example/token")
    monkeypatch.setenv("MOT_API_KEY", "key")


def test_create_lookup_requires_admin(auth_client: FlaskClient) -> None:
    assert auth_client.post("/api/vehicle-records", json={"registration": "A1XYZ"}).status_code == 403


def test_create_lookup_requires_registration(admin_client: FlaskClient) -> None:
    assert admin_client.post("/api/vehicle-records", json={}).status_code == 400


def test_create_lookup_saves_both(
    admin_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, both_enabled: None
) -> None:
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)
    monkeypatch.setattr(ves, "fetch_ves", lambda reg: TAX_PAYLOAD)
    r = admin_client.post("/api/vehicle-records", json={"registration": "A1 XYZ"})
    assert r.status_code == 201
    assert r.json["make"] == "VOLKSWAGEN"
    assert r.json["saved"]["dvsa"]["make"] == "VOLKSWAGEN"
    assert r.json["saved"]["ves"]["tax_status"] == "Taxed"
    assert r.json["saved"]["ves"]["mot_status"] == "Vehicle A1XYZ has a valid MOT certificate"
    assert r.json["errors"] == []

    body = admin_client.get("/api/vehicle-records").json
    assert body["total_ves"] == 1
    item = body["items"][0]
    # A DVSA lookup and one VES lookup, grouped by plate.
    assert item["record_count"] == 2  # dvsa + ves
    assert item["dvsa_count"] == 1
    assert item["ves_count"] == 1
    assert item["vehicle_id"] is None  # standalone


def test_create_lookup_partial_failure_still_saves_the_other(
    admin_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, both_enabled: None
) -> None:
    # DVSA succeeds; DVLA (VES) fails — the DVSA record is still saved and the error reported.
    monkeypatch.setattr(mot, "fetch_vehicle", lambda reg: SAMPLE)

    def ves_boom(reg: str) -> dict[str, Any]:
        raise ves.VesError("No vehicle found", 404)

    monkeypatch.setattr(ves, "fetch_ves", ves_boom)
    r = admin_client.post("/api/vehicle-records", json={"registration": "A1XYZ"})
    assert r.status_code == 201
    assert r.json["saved"]["dvsa"] is not None
    assert r.json["saved"]["ves"] is None
    assert any("DVLA" in e for e in r.json["errors"])

    item = admin_client.get("/api/vehicle-records").json["items"][0]
    assert item["dvsa_count"] == 1
    assert item["ves_count"] == 0


def test_create_lookup_both_fail_is_404(
    admin_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, both_enabled: None
) -> None:
    def mot_boom(reg: str) -> dict[str, Any]:
        raise mot.MotError("No MOT record found", 404)

    def ves_boom(reg: str) -> dict[str, Any]:
        raise ves.VesError("No vehicle found", 404)

    monkeypatch.setattr(mot, "fetch_vehicle", mot_boom)
    monkeypatch.setattr(ves, "fetch_ves", ves_boom)
    r = admin_client.post("/api/vehicle-records", json={"registration": "A1XYZ"})
    assert r.status_code == 404
    assert "MOT record" in r.json["error"]
    assert "No vehicle found" in r.json["error"]


def test_create_lookup_only_ves_when_mot_unconfigured(
    admin_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # DVSA needs credentials; when they're absent, only the always-available VES runs.
    monkeypatch.setattr(mot, "is_configured", lambda: False)
    monkeypatch.setattr(ves, "fetch_ves", lambda reg: TAX_PAYLOAD)
    r = admin_client.post("/api/vehicle-records", json={"registration": "A1XYZ"})
    assert r.status_code == 201
    assert r.json["saved"]["dvsa"] is None
    assert r.json["saved"]["ves"] is not None
