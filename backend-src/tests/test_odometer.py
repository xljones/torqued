"""Tests for /api/vehicles/<id>/odometer: manual mileage logs."""
import pytest
from flask.testing import FlaskClient

from tests.test_vehicles import mk_vehicle


def test_create_converts_miles(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    r = auth_client.post(f"/api/vehicles/{v['id']}/odometer", json={
        "date": "2025-06-01", "odometer": 100, "unit": "mi", "note": "Trip done",
    })
    assert r.status_code == 201
    assert r.json["odometer_km"] == pytest.approx(160.9344)
    assert r.json["unit"] == "mi"
    assert r.json["note"] == "Trip done"


def test_create_validation(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    url = f"/api/vehicles/{v['id']}/odometer"
    assert auth_client.post(url, json={"odometer": 1}).status_code == 400
    assert auth_client.post(url, json={"date": "2025-06-01"}).status_code == 400
    assert auth_client.post(url, json={
        "date": "2025-06-01", "odometer": "lots",
    }).status_code == 400
    assert auth_client.post(url, json={
        "date": "2025-06-01", "odometer": 1, "unit": "leagues",
    }).status_code == 400


def test_create_vehicle_404(auth_client: FlaskClient) -> None:
    r = auth_client.post("/api/vehicles/999/odometer",
                         json={"date": "2025-06-01", "odometer": 1})
    assert r.status_code == 404


def test_list_newest_first(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    for d, km in (("2025-01-01", 100), ("2025-03-01", 300), ("2025-02-01", 200)):
        auth_client.post(f"/api/vehicles/{v['id']}/odometer", json={
            "date": d, "odometer": km, "unit": "km",
        })
    r = auth_client.get(f"/api/vehicles/{v['id']}/odometer")
    assert r.status_code == 200
    assert [log["odometer_km"] for log in r.json] == [300.0, 200.0, 100.0]


def test_list_vehicle_404(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/vehicles/999/odometer").status_code == 404


def test_delete(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    log = auth_client.post(f"/api/vehicles/{v['id']}/odometer", json={
        "date": "2025-06-01", "odometer": 1, "unit": "km",
    }).json
    assert auth_client.delete(f"/api/odometer/{log['id']}").status_code == 204
    assert auth_client.delete(f"/api/odometer/{log['id']}").status_code == 404
