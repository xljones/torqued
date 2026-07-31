"""Tests for /api/vehicles: CRUD, specs, mileage, history, reminders endpoint."""
from flask.testing import FlaskClient


def mk_vehicle(client: FlaskClient, **overrides) -> dict:
    if "garage_id" not in overrides:
        garages = client.get("/api/garages").json
        overrides["garage_id"] = garages[0]["id"]
    body = {"name": "Street Triple", "kind": "motorcycle", **overrides}
    r = client.post("/api/vehicles", json=body)
    assert r.status_code == 201, r.json
    return r.json


# ── create ────────────────────────────────────────────────────────────────────

def test_create_minimal(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client, kind="car")
    assert v["name"] == "Street Triple"
    assert v["kind"] == "car"
    assert v["odometer_unit"] == "mi"
    assert v["archived"] == 0


def test_create_full(auth_client: FlaskClient) -> None:
    v = mk_vehicle(
        auth_client,
        make="Triumph", model="Street Triple RS", year="2021",
        registration="LB21 XYZ", vin="SMTT123", colour="Silver",
        fuel_type="Petrol", odometer_unit="km", purchase_date="2022-03-12",
        tyre_size_front="120/70 ZR17", tyre_size_rear="180/55 ZR17",
        tyre_pressure_front_psi=36, tyre_pressure_rear_psi="42.5",
        notes="Quickshifter", archived=False,
    )
    assert v["year"] == 2021
    assert v["tyre_pressure_rear_psi"] == 42.5
    assert v["odometer_unit"] == "km"


def test_create_persists_mot_override_fields(auth_client: FlaskClient) -> None:
    v = mk_vehicle(
        auth_client, engine_size="765",
        first_used_date="2021-03-01", registration_date="2021-03-05",
    )
    got = auth_client.get(f"/api/vehicles/{v['id']}").json
    assert got["engine_size"] == "765"
    assert got["first_used_date"] == "2021-03-01"
    assert got["registration_date"] == "2021-03-05"
    # No MOT fetched, so there is no baseline to fall back to
    assert got["mot_baseline"] is None
    # …and with neither source stored there are no DVLA fields or provenance tags.
    assert got["ves_baseline"] is None
    assert got["field_sources"] == {}


def test_detail_exposes_ves_baseline_and_field_sources(auth_client: FlaskClient) -> None:
    import json

    from torqued.db import get_db
    from torqued.models import DvsaVehicle
    from torqued.repositories.ves_repository import VesRepository

    v = mk_vehicle(auth_client, registration="A1 XYZ")
    with get_db() as db:
        # A DVSA snapshot (make/year) plus a DVLA VES lookup of the same vehicle,
        # differently formatted, so field_sources exercises the "both agree" path.
        db.add(DvsaVehicle(
            vehicle_id=v["id"], registration="A1XYZ", make="FORD", manufacture_year=2003,
            raw_json=json.dumps({"make": "FORD", "manufactureYear": 2003}),
        ))
        VesRepository(db).replace_for_vehicle(v["id"], {
            "registration": "A1XYZ", "tax_status": "Taxed", "make": "FORD",
            "year_of_manufacture": "2003", "cylinder_capacity": "1781 cc",
            "co2_emissions": "204 g/km", "euro_status": "Not available",
        })
    got = auth_client.get(f"/api/vehicles/{v['id']}").json
    # DVLA-only field surfaces in ves_baseline; "Not available" is dropped.
    assert got["ves_baseline"]["co2_emissions"] == "204 g/km"
    assert "euro_status" not in got["ves_baseline"]
    # DVSA + DVLA agree once normalised → both tags; CO₂ is DVLA-only.
    assert got["field_sources"]["make"] == ["dvsa", "dvla"]
    assert got["field_sources"]["year"] == ["dvsa", "dvla"]
    assert got["field_sources"]["co2_emissions"] == ["dvla"]


def test_clear_override_field(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client, make="Triumph", engine_size="765")
    body = {**v, "engine_size": None}
    assert auth_client.put(f"/api/vehicles/{v['id']}", json=body).status_code == 200
    assert auth_client.get(f"/api/vehicles/{v['id']}").json["engine_size"] is None


def test_create_requires_name(auth_client: FlaskClient) -> None:
    garage_id = auth_client.get("/api/garages").json[0]["id"]
    r = auth_client.post("/api/vehicles", json={"name": "  ", "garage_id": garage_id})
    assert r.status_code == 400
    assert "name" in r.json["error"]


def test_create_requires_garage_id(auth_client: FlaskClient) -> None:
    r = auth_client.post("/api/vehicles", json={"name": "Bike"})
    assert r.status_code == 400
    assert "garage_id" in r.json["error"]


def test_create_in_inaccessible_garage_404(auth_client: FlaskClient) -> None:
    assert auth_client.post(
        "/api/vehicles", json={"name": "Bike", "garage_id": 999}
    ).status_code == 404


def test_create_rejects_bad_kind(auth_client: FlaskClient) -> None:
    garage_id = auth_client.get("/api/garages").json[0]["id"]
    r = auth_client.post("/api/vehicles", json={"name": "Boat", "kind": "boat", "garage_id": garage_id})
    assert r.status_code == 400


def test_create_rejects_bad_unit(auth_client: FlaskClient) -> None:
    garage_id = auth_client.get("/api/garages").json[0]["id"]
    r = auth_client.post(
        "/api/vehicles", json={"name": "Bike", "odometer_unit": "leagues", "garage_id": garage_id}
    )
    assert r.status_code == 400


def test_create_rejects_non_numeric_year(auth_client: FlaskClient) -> None:
    garage_id = auth_client.get("/api/garages").json[0]["id"]
    r = auth_client.post(
        "/api/vehicles", json={"name": "Bike", "year": "twenty", "garage_id": garage_id}
    )
    assert r.status_code == 400


def test_create_rejects_non_numeric_pressure(auth_client: FlaskClient) -> None:
    garage_id = auth_client.get("/api/garages").json[0]["id"]
    r = auth_client.post(
        "/api/vehicles",
        json={"name": "Bike", "tyre_pressure_front_psi": "squishy", "garage_id": garage_id},
    )
    assert r.status_code == 400


# ── list ──────────────────────────────────────────────────────────────────────

def test_list_excludes_archived_by_default(auth_client: FlaskClient) -> None:
    mk_vehicle(auth_client)
    archived = mk_vehicle(auth_client, name="Sold bike")
    auth_client.put(f"/api/vehicles/{archived['id']}",
                    json={"name": "Sold bike", "archived": True})
    names = [v["name"] for v in auth_client.get("/api/vehicles").json]
    assert "Sold bike" not in names
    all_names = [v["name"] for v in auth_client.get("/api/vehicles?archived=1").json]
    assert "Sold bike" in all_names


def test_list_garage_filter(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    listed = auth_client.get(f"/api/vehicles?garage_id={v['garage_id']}").json
    assert [x["id"] for x in listed] == [v["id"]]
    assert listed[0]["garage_name"] == "Test Garage"
    assert auth_client.get("/api/vehicles?garage_id=999").status_code == 404
    assert auth_client.get("/api/vehicles?garage_id=abc").status_code == 400


def test_list_includes_counts_and_latest_odometer(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    auth_client.post(f"/api/vehicles/{v['id']}/services", json={
        "date": "2025-01-01", "title": "Oil change", "odometer": 1000, "odometer_unit": "km",
    })
    listed = auth_client.get("/api/vehicles").json[0]
    assert listed["service_count"] == 1
    assert listed["latest_odometer"]["odometer_km"] == 1000.0


# ── get / update / delete ─────────────────────────────────────────────────────

def test_get_detail(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    r = auth_client.get(f"/api/vehicles/{v['id']}")
    assert r.status_code == 200
    assert r.json["specs"] == []
    assert r.json["photos"] == []
    assert r.json["reminders"] == []
    assert r.json["latest_odometer"] is None


def test_get_404(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/vehicles/999").status_code == 404


def test_repository_get_detail_missing(auth_client: FlaskClient) -> None:
    from torqued.db import get_db
    from torqued.repositories.vehicle_repository import VehicleRepository
    with get_db() as db:
        assert VehicleRepository(db).get_detail(999) is None


def test_update(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    r = auth_client.put(f"/api/vehicles/{v['id']}", json={"name": "Renamed", "kind": "car"})
    assert r.status_code == 200
    assert r.json["name"] == "Renamed"


def test_update_404(auth_client: FlaskClient) -> None:
    assert auth_client.put("/api/vehicles/999", json={"name": "X"}).status_code == 404


def test_update_validation(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    assert auth_client.put(f"/api/vehicles/{v['id']}", json={}).status_code == 400


def test_delete(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    assert auth_client.delete(f"/api/vehicles/{v['id']}").status_code == 204
    assert auth_client.get(f"/api/vehicles/{v['id']}").status_code == 404


def test_delete_404(auth_client: FlaskClient) -> None:
    assert auth_client.delete("/api/vehicles/999").status_code == 404


# ── specs ─────────────────────────────────────────────────────────────────────

def test_replace_specs(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    r = auth_client.put(f"/api/vehicles/{v['id']}/specs", json={"specs": [
        {"name": "Engine oil", "value": "10W-40"},
        {"name": "Chain slack", "value": "25 mm"},
    ]})
    assert r.status_code == 200
    assert [s["name"] for s in r.json] == ["Engine oil", "Chain slack"]
    # Replacing again removes old entries
    r = auth_client.put(f"/api/vehicles/{v['id']}/specs", json={"specs": [
        {"name": "Battery", "value": "YTX9-BS"},
    ]})
    assert [s["name"] for s in r.json] == ["Battery"]


def test_replace_specs_validation(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    assert auth_client.put(f"/api/vehicles/{v['id']}/specs",
                           json={"specs": "oil"}).status_code == 400
    assert auth_client.put(f"/api/vehicles/{v['id']}/specs",
                           json={"specs": [{"value": "no name"}]}).status_code == 400


def test_replace_specs_404(auth_client: FlaskClient) -> None:
    assert auth_client.put("/api/vehicles/999/specs", json={"specs": []}).status_code == 404


# ── mileage series ────────────────────────────────────────────────────────────

def test_mileage_series_merges_sources(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    auth_client.post(f"/api/vehicles/{v['id']}/services", json={
        "date": "2025-01-01", "title": "Service", "odometer": 100, "odometer_unit": "km",
    })
    auth_client.post(f"/api/vehicles/{v['id']}/odometer", json={
        "date": "2025-02-01", "odometer": 200, "unit": "km",
    })
    r = auth_client.get(f"/api/vehicles/{v['id']}/mileage")
    assert r.status_code == 200
    assert [(p["source"], p["odometer_km"]) for p in r.json] == [
        ("service", 100.0), ("manual", 200.0),
    ]


def test_mileage_series_404(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/vehicles/999/mileage").status_code == 404


# ── history / revert ──────────────────────────────────────────────────────────

def test_history_and_revert(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client, name="Original")
    auth_client.put(f"/api/vehicles/{v['id']}", json={"name": "Changed", "kind": "motorcycle"})
    history = auth_client.get(f"/api/vehicles/{v['id']}/history").json
    assert [h["name"] for h in history] == ["Changed", "Original"]
    assert history[0]["changed_by_username"] == "testuser"

    r = auth_client.post(f"/api/vehicles/{v['id']}/revert/{history[1]['id']}")
    assert r.status_code == 200
    assert r.json["name"] == "Original"


def test_revert_unknown_version(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    assert auth_client.post(f"/api/vehicles/{v['id']}/revert/999").status_code == 404


# ── reminders endpoint ────────────────────────────────────────────────────────

def test_history_404(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/vehicles/999/history").status_code == 404


def test_reminders_garage_filter(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    auth_client.post(f"/api/vehicles/{v['id']}/services", json={
        "date": "2020-01-01", "title": "Oil change", "next_due_date": "2020-06-01",
    })
    assert len(auth_client.get(f"/api/reminders?garage_id={v['garage_id']}").json) == 1
    assert auth_client.get("/api/reminders?garage_id=999").status_code == 404
    assert auth_client.get("/api/reminders?garage_id=abc").status_code == 400


def test_all_reminders_endpoint(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    auth_client.post(f"/api/vehicles/{v['id']}/services", json={
        "date": "2020-01-01", "title": "Oil change", "category": "Oil change",
        "next_due_date": "2020-06-01",
    })
    r = auth_client.get("/api/reminders")
    assert r.status_code == 200
    assert r.json[0]["status"] == "overdue"
    assert r.json[0]["vehicle_name"] == "Street Triple"
