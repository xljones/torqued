"""Tests for the DVLA VES current-MOT-status record (MotStatusRepository + endpoints).

The MOT-status record is scraped from the same VES page as the tax record (see test_tax.py)
but stored in its own ``vehicle_mot_status`` table, mirroring the tax record's retain-on-
delete / relink behaviour. Reminder supplementation lives in test_mot.py; the records-page
grouping in test_records.py.
"""
from typing import Any

import pytest
from flask.testing import FlaskClient

from tests.test_vehicles import mk_vehicle
from torqued import tax
from torqued.db import get_db
from torqued.repositories.mot_status_repository import MotStatusRepository

PAYLOAD = {
    "registration": "A1XYZ",
    "tax_status": "SORN",
    "tax_due_date": None,
    "mot_status": "Vehicle A1XYZ has a valid MOT certificate",
    "mot_expiry_date": "2027-07-29",
}


def test_replace_and_get_for_vehicle(garage: dict[str, Any]) -> None:
    from torqued.repositories.vehicle_repository import VehicleRepository

    with get_db() as db:
        v = VehicleRepository(db).create(garage["id"], {"name": "Bike"})
        MotStatusRepository(db).replace_for_vehicle(v["id"], PAYLOAD)
    with get_db() as db:
        snap = MotStatusRepository(db).get_for_vehicle(v["id"])
    assert snap is not None
    assert snap["mot_status"] == "Vehicle A1XYZ has a valid MOT certificate"
    assert snap["mot_expiry_date"] == "2027-07-29"
    # raw holds only the MOT facet of the VES payload — the tax fields live on the separate
    # vehicle_tax record, so the two records aren't identical.
    assert snap["raw"] == {
        "registration": "A1XYZ",
        "mot_status": "Vehicle A1XYZ has a valid MOT certificate",
        "mot_expiry_date": "2027-07-29",
    }
    assert "tax_status" not in snap["raw"]


def test_refresh_keeps_previous_lookup_as_history(garage: dict[str, Any]) -> None:
    from sqlalchemy import select

    from torqued.models import VehicleMotStatus
    from torqued.repositories.vehicle_repository import VehicleRepository

    with get_db() as db:
        v = VehicleRepository(db).create(garage["id"], {"name": "Bike"})
        MotStatusRepository(db).replace_for_vehicle(v["id"], PAYLOAD)
    with get_db() as db:
        MotStatusRepository(db).replace_for_vehicle(v["id"], PAYLOAD)
    with get_db() as db:
        rows = db.scalars(select(VehicleMotStatus).order_by(VehicleMotStatus.id)).all()
        assert [r.vehicle_id for r in rows] == [None, v["id"]]  # older detached, newer live


def test_record_retained_after_vehicle_delete(garage: dict[str, Any]) -> None:
    from sqlalchemy import select

    from torqued.models import VehicleMotStatus
    from torqued.repositories.vehicle_repository import VehicleRepository

    with get_db() as db:
        v = VehicleRepository(db).create(garage["id"], {"name": "Doomed"})
        MotStatusRepository(db).replace_for_vehicle(v["id"], {**PAYLOAD, "registration": "OLD123"})
    with get_db() as db:
        assert VehicleRepository(db).delete(v["id"]) is True
        assert MotStatusRepository(db).get_for_vehicle(v["id"]) is None
        row = db.scalars(select(VehicleMotStatus)).one()
        assert row.vehicle_id is None
        assert row.registration == "OLD123"


def test_relink_blank_registration_is_false(garage: dict[str, Any]) -> None:
    from torqued.repositories.vehicle_repository import VehicleRepository

    with get_db() as db:
        v = VehicleRepository(db).create(garage["id"], {"name": "Car"})
        assert MotStatusRepository(db).relink_detached(v["id"], "   ") is False


def test_standalone_lookup_links_when_vehicle_added_later(
    auth_client: FlaskClient, garage: dict[str, Any]
) -> None:
    with get_db() as db:
        MotStatusRepository(db).store_detached_lookup(PAYLOAD)
    v = mk_vehicle(auth_client, registration="A1 XYZ")
    with get_db() as db:
        snap = MotStatusRepository(db).get_for_vehicle(v["id"])
    assert snap is not None and snap["mot_expiry_date"] == "2027-07-29"


def test_tax_refresh_also_writes_mot_status(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # One VES refresh persists both records and returns both; the MOT-status endpoint then
    # serves the snapshot.
    monkeypatch.setattr(tax, "is_configured", lambda: True)
    monkeypatch.setattr(tax, "fetch_tax", lambda reg: PAYLOAD)
    v = mk_vehicle(auth_client, registration="A1 XYZ")
    r = auth_client.post(f"/api/vehicles/{v['id']}/tax/refresh")
    assert r.status_code == 200, r.json
    assert r.json["mot_status"]["mot_expiry_date"] == "2027-07-29"

    got = auth_client.get(f"/api/vehicles/{v['id']}/mot-status").json
    assert got["mot_status"]["mot_status"] == "Vehicle A1XYZ has a valid MOT certificate"


def test_get_mot_status_out_of_scope_is_404(auth_client: FlaskClient) -> None:
    # A vehicle the user can't see (here, one that doesn't exist) hides its existence.
    assert auth_client.get("/api/vehicles/999999/mot-status").status_code == 404


def test_disconnect_clears_mot_status(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tax, "is_configured", lambda: True)
    monkeypatch.setattr(tax, "fetch_tax", lambda reg: PAYLOAD)
    v = mk_vehicle(auth_client, registration="A1 XYZ")
    auth_client.post(f"/api/vehicles/{v['id']}/tax/refresh")
    assert auth_client.get(f"/api/vehicles/{v['id']}/mot-status").json["mot_status"] is not None

    body = {"name": v["name"], "kind": v["kind"], "registration": "B2 YYY", "disconnect_mot": True}
    assert auth_client.put(f"/api/vehicles/{v['id']}", json=body).status_code == 200
    assert auth_client.get(f"/api/vehicles/{v['id']}/mot-status").json["mot_status"] is None
