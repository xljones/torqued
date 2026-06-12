"""Tests for /api/export/vehicles/<id>/pdf and the pdf_report builder."""
import io

from flask.testing import FlaskClient
from PIL import Image as PILImage

from tests.test_services import mk_service
from tests.test_vehicles import mk_vehicle


def _png(width: int = 10, height: int = 10) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (width, height), "red").save(buf, "PNG")
    return buf.getvalue()


def _upload(client: FlaskClient, vehicle_id: int, filename: str, content: bytes, **form) -> None:
    r = client.post(
        f"/api/vehicles/{vehicle_id}/photos",
        data={"file": (io.BytesIO(content), filename), **form},
        content_type="multipart/form-data",
    )
    assert r.status_code == 201, r.json


def _store_mot(vehicle_id: int) -> None:
    """Persist a DVSA snapshot directly, mirroring a refresh."""
    from torqued.db import get_db
    from torqued.repositories.mot_repository import MotRepository

    payload = {
        "registration": "AB12CDE",
        "make": "VOLKSWAGEN",
        "model": "PASSAT",
        "manufactureYear": 2018,
        "fuelType": "Diesel",
        "primaryColour": "Blue",
        "engineSize": "1968",
        "hasOutstandingRecall": "No",
        "motTestDueDate": "2026-11-04",
        "motTests": [
            {
                "completedDate": "2024-11-05T10:01:00.000Z", "testResult": "PASSED",
                "expiryDate": "2025-11-04", "odometerValue": 42000, "odometerUnit": "MI",
                "motTestNumber": "1234", "dataSource": "DVSA",
                "defects": [{"text": "Tyre worn", "type": "ADVISORY", "dangerous": False}],
            },
            {
                "completedDate": "2023-10-30T09:00:00.000Z", "testResult": "FAILED",
                "expiryDate": None, "odometerValue": None, "odometerUnit": None,
                "motTestNumber": "1233", "dataSource": "DVSA",
                "defects": [{"text": "Brake pipe corroded", "type": "MAJOR", "dangerous": True}],
            },
        ],
    }
    with get_db() as db:
        MotRepository(db).replace_for_vehicle(vehicle_id, payload)


def _full_vehicle(client: FlaskClient) -> dict:
    """A vehicle exercising every populated PDF section."""
    # Front pressure set, rear left blank: exercises both pressure branches.
    v = mk_vehicle(
        client, name="Daily", kind="car", registration="AB12CDE", colour="Blue",
        notes="Bought used.", tyre_size_front="120/70", tyre_size_rear="180/55",
        tyre_pressure_front_psi=34, odometer_unit="mi",
    )
    vid = v["id"]
    # Specs.
    client.put(f"/api/vehicles/{vid}/specs",
               json={"specs": [{"name": "Oil", "value": "5W-30"}]})
    # A rich log (date+km reminder + fault codes), a date-only reminder, and a bare one.
    mk_service(
        client, vid, title="Major service", category="engine", performed_by="Me",
        cost=199.99, odometer=42000, odometer_unit="mi", description="Full service.",
        next_due_date="2027-01-01", next_due_distance=50000, fault_codes=["P0420", "ZZ999"],
    )
    mk_service(client, vid, title="MOT", category="mot", next_due_date="2027-03-01")
    mk_service(client, vid, title="Wash", category="cosmetic")
    # Manual odometer logs so the timeline has >= 2 points (chart path).
    client.post(f"/api/vehicles/{vid}/odometer",
                json={"date": "2024-06-01", "odometer": 41000, "unit": "mi"})
    client.post(f"/api/vehicles/{vid}/odometer",
                json={"date": "2024-12-01", "odometer": 43000, "unit": "mi"})
    # Two photos: a wide one (triggers downscale) with a caption, one without.
    _upload(client, vid, "wide.png", _png(2000, 100), caption="Front view")
    _upload(client, vid, "plain.png", _png(20, 20))
    _store_mot(vid)
    return v


def test_pdf_full_vehicle_with_photos(auth_client: FlaskClient) -> None:
    v = _full_vehicle(auth_client)
    r = auth_client.get(f"/api/export/vehicles/{v['id']}/pdf?include_photos=1")
    assert r.status_code == 200
    assert r.mimetype == "application/pdf"
    assert "attachment" in r.headers["Content-Disposition"]
    assert "torqued-AB12CDE-" in r.headers["Content-Disposition"]
    assert r.data[:4] == b"%PDF"


def test_pdf_empty_vehicle_no_mot_no_photos(auth_client: FlaskClient) -> None:
    # Minimal vehicle: no services, specs, tyres, mileage, MOT, or photos.
    v = mk_vehicle(auth_client, name="Bare", registration=None)
    r = auth_client.get(f"/api/export/vehicles/{v['id']}/pdf?include_photos=true")
    assert r.status_code == 200
    assert r.data[:4] == b"%PDF"
    # No registration -> filename falls back to the vehicle name.
    assert "torqued-Bare-" in r.headers["Content-Disposition"]


def test_pdf_without_photos_flag(auth_client: FlaskClient) -> None:
    v = _full_vehicle(auth_client)
    r = auth_client.get(f"/api/export/vehicles/{v['id']}/pdf")
    assert r.status_code == 200
    assert r.data[:4] == b"%PDF"


def test_pdf_single_point_and_unreadable_photo(auth_client: FlaskClient) -> None:
    # One service => one mileage point (no chart), plus an unreadable photo file.
    v = mk_vehicle(auth_client, name="One")
    mk_service(auth_client, v["id"], title="Tyres", odometer=1000, odometer_unit="mi")
    _upload(auth_client, v["id"], "broken.png", b"not a real image")
    r = auth_client.get(f"/api/export/vehicles/{v['id']}/pdf?include_photos=1")
    assert r.status_code == 200
    assert r.data[:4] == b"%PDF"


def test_fmt_engine_size() -> None:
    from torqued.pdf_report import _EMDASH, _fmt_engine_size

    # Bare DVSA number gains a unit; a value that already carries one passes through.
    assert _fmt_engine_size("1968") == "1968 cc"
    assert _fmt_engine_size("1000 cc") == "1000 cc"
    # Unset renders the em-dash.
    assert _fmt_engine_size(None) == _EMDASH


def test_pdf_vehicle_out_of_scope(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/export/vehicles/999/pdf").status_code == 404


def test_pdf_readonly_member_allowed(
    readonly_client: FlaskClient, auth_client: FlaskClient
) -> None:
    v = mk_vehicle(auth_client, name="Shared")
    r = readonly_client.get(f"/api/export/vehicles/{v['id']}/pdf")
    assert r.status_code == 200
    assert r.data[:4] == b"%PDF"
