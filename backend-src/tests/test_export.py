"""Tests for /api/export/services: CSV/TSV/JSON exports."""
import json

from flask.testing import FlaskClient

from tests.test_services import mk_service
from tests.test_vehicles import mk_vehicle


def _setup(client: FlaskClient) -> tuple[dict, dict]:
    v1 = mk_vehicle(client, name="Bike")
    v2 = mk_vehicle(client, name="Car", kind="car")
    mk_service(client, v1["id"], title="Chain adjust", odometer=100, odometer_unit="km")
    mk_service(client, v2["id"], title="MOT")
    return v1, v2


def test_export_csv(auth_client: FlaskClient) -> None:
    _setup(auth_client)
    r = auth_client.get("/api/export/services")
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    assert "attachment" in r.headers["Content-Disposition"]
    lines = r.data.decode().strip().splitlines()
    assert lines[0].startswith("garage,vehicle,make,model,registration,date,title")
    assert len(lines) == 3


def test_export_tsv(auth_client: FlaskClient) -> None:
    _setup(auth_client)
    r = auth_client.get("/api/export/services?format=tsv")
    assert r.status_code == 200
    assert r.mimetype == "text/tab-separated-values"
    assert "\t" in r.data.decode().splitlines()[0]


def test_export_json(auth_client: FlaskClient) -> None:
    _setup(auth_client)
    r = auth_client.get("/api/export/services?format=json")
    assert r.status_code == 200
    rows = json.loads(r.data)
    assert {row["title"] for row in rows} == {"Chain adjust", "MOT"}


def test_export_filtered_by_vehicle(auth_client: FlaskClient) -> None:
    v1, _ = _setup(auth_client)
    r = auth_client.get(f"/api/export/services?vehicle_id={v1['id']}&format=json")
    rows = json.loads(r.data)
    assert [row["title"] for row in rows] == ["Chain adjust"]


def test_export_bad_vehicle_id(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/export/services?vehicle_id=abc").status_code == 400


def test_export_unknown_format(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/export/services?format=xml").status_code == 400


def test_export_garage_filter(auth_client: FlaskClient) -> None:
    _setup(auth_client)
    garage_id = auth_client.get("/api/garages").json[0]["id"]
    r = auth_client.get(f"/api/export/services?garage_id={garage_id}&format=json")
    assert len(json.loads(r.data)) == 2
    assert auth_client.get("/api/export/services?garage_id=999").status_code == 404
    assert auth_client.get("/api/export/services?garage_id=abc").status_code == 400


def test_export_vehicle_out_of_scope(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/export/services?vehicle_id=999").status_code == 404


def test_export_empty(auth_client: FlaskClient) -> None:
    r = auth_client.get("/api/export/services")
    assert r.status_code == 200
    assert r.data.decode().strip() == ""
