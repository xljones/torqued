"""Tests for /api/services: CRUD, unit conversion, reminders, history."""
from datetime import date, timedelta

import pytest
from flask.testing import FlaskClient

from tests.test_vehicles import mk_vehicle


def mk_service(client: FlaskClient, vehicle_id: int, **overrides) -> dict:
    body = {"date": "2025-01-15", "title": "Oil change", **overrides}
    r = client.post(f"/api/vehicles/{vehicle_id}/services", json=body)
    assert r.status_code == 201, r.json
    return r.json


# ── create ────────────────────────────────────────────────────────────────────

def test_create_converts_miles_to_km(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_service(auth_client, v["id"], odometer=100, odometer_unit="mi",
                   next_due_distance=200)
    assert s["odometer_km"] == pytest.approx(160.9344)
    assert s["odometer_unit"] == "mi"
    assert s["next_due_km"] == pytest.approx(321.8688)


def test_create_km_passthrough(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_service(auth_client, v["id"], odometer="500", odometer_unit="km",
                   cost="12.50", category="Tyres", performed_by="Me",
                   description="Front tyre", next_due_date="2026-01-01")
    assert s["odometer_km"] == 500.0
    assert s["cost"] == 12.5
    assert s["vehicle_name"] == "Street Triple"


def test_create_without_odometer(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_service(auth_client, v["id"])
    assert s["odometer_km"] is None
    assert s["odometer_unit"] is None


def test_create_requires_date_and_title(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    r = auth_client.post(f"/api/vehicles/{v['id']}/services", json={"title": "x"})
    assert r.status_code == 400
    r = auth_client.post(f"/api/vehicles/{v['id']}/services", json={"date": "2025-01-01"})
    assert r.status_code == 400


def test_create_rejects_non_numeric(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    r = auth_client.post(f"/api/vehicles/{v['id']}/services", json={
        "date": "2025-01-01", "title": "x", "odometer": "many",
    })
    assert r.status_code == 400
    r = auth_client.post(f"/api/vehicles/{v['id']}/services", json={
        "date": "2025-01-01", "title": "x", "cost": "free",
    })
    assert r.status_code == 400


def test_create_vehicle_404(auth_client: FlaskClient) -> None:
    r = auth_client.post("/api/vehicles/999/services",
                         json={"date": "2025-01-01", "title": "x"})
    assert r.status_code == 404


# ── list / get ────────────────────────────────────────────────────────────────

def test_list_all_and_per_vehicle(auth_client: FlaskClient) -> None:
    v1 = mk_vehicle(auth_client, name="Bike")
    v2 = mk_vehicle(auth_client, name="Car", kind="car")
    mk_service(auth_client, v1["id"], title="Chain adjust")
    mk_service(auth_client, v2["id"], title="MOT")
    assert len(auth_client.get("/api/services").json) == 2
    per = auth_client.get(f"/api/vehicles/{v1['id']}/services").json
    assert [s["title"] for s in per] == ["Chain adjust"]


def test_list_garage_filter(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    mk_service(auth_client, v["id"])
    listed = auth_client.get(f"/api/services?garage_id={v['garage_id']}").json
    assert len(listed) == 1
    assert auth_client.get("/api/services?garage_id=999").status_code == 404
    assert auth_client.get("/api/services?garage_id=abc").status_code == 400


def test_history_404(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/services/999/history").status_code == 404


def test_list_per_vehicle_404(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/vehicles/999/services").status_code == 404


def test_get_includes_photos(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_service(auth_client, v["id"])
    r = auth_client.get(f"/api/services/{s['id']}")
    assert r.status_code == 200
    assert r.json["photos"] == []


def test_get_404(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/services/999").status_code == 404


# ── update / delete ───────────────────────────────────────────────────────────

def test_update(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_service(auth_client, v["id"])
    r = auth_client.put(f"/api/services/{s['id']}", json={
        "date": "2025-02-01", "title": "Oil + filter", "odometer": 1000,
        "odometer_unit": "km",
    })
    assert r.status_code == 200
    assert r.json["title"] == "Oil + filter"
    assert r.json["odometer_km"] == 1000.0


def test_update_404_and_validation(auth_client: FlaskClient) -> None:
    assert auth_client.put("/api/services/999",
                           json={"date": "2025-01-01", "title": "x"}).status_code == 404
    v = mk_vehicle(auth_client)
    s = mk_service(auth_client, v["id"])
    assert auth_client.put(f"/api/services/{s['id']}", json={}).status_code == 400


def test_delete(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_service(auth_client, v["id"])
    assert auth_client.delete(f"/api/services/{s['id']}").status_code == 204
    assert auth_client.delete(f"/api/services/{s['id']}").status_code == 404


# ── history / revert ──────────────────────────────────────────────────────────

def test_history_and_revert(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_service(auth_client, v["id"], title="Original title")
    auth_client.put(f"/api/services/{s['id']}",
                    json={"date": s["date"], "title": "New title"})
    history = auth_client.get(f"/api/services/{s['id']}/history").json
    assert [h["title"] for h in history] == ["New title", "Original title"]

    r = auth_client.post(f"/api/services/{s['id']}/revert/{history[1]['id']}")
    assert r.status_code == 200
    assert r.json["title"] == "Original title"


def test_revert_unknown_version(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_service(auth_client, v["id"])
    assert auth_client.post(f"/api/services/{s['id']}/revert/999").status_code == 404


# ── performers ────────────────────────────────────────────────────────────────

def test_performers_distinct_sorted(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    mk_service(auth_client, v["id"], performed_by="Me")
    mk_service(auth_client, v["id"], performed_by="A1 Garage")
    mk_service(auth_client, v["id"], performed_by="Me")
    mk_service(auth_client, v["id"])  # no performer
    assert auth_client.get("/api/services/performers").json == ["A1 Garage", "Me"]


# ── reminders ─────────────────────────────────────────────────────────────────

def _vehicle_reminders(client: FlaskClient, vehicle_id: int) -> list[dict]:
    return client.get(f"/api/vehicles/{vehicle_id}").json["reminders"]


def test_reminder_overdue_by_date(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    mk_service(auth_client, v["id"], category="Service", next_due_date="2020-01-01")
    [r] = _vehicle_reminders(auth_client, v["id"])
    assert r["status"] == "overdue"


def test_reminder_due_soon_by_date(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    soon = (date.today() + timedelta(days=10)).isoformat()
    mk_service(auth_client, v["id"], category="Service", next_due_date=soon)
    [r] = _vehicle_reminders(auth_client, v["id"])
    assert r["status"] == "due_soon"


def test_reminder_upcoming(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    far = (date.today() + timedelta(days=200)).isoformat()
    mk_service(auth_client, v["id"], category="Service", next_due_date=far)
    [r] = _vehicle_reminders(auth_client, v["id"])
    assert r["status"] == "upcoming"


def test_reminder_due_soon_uses_the_two_thousand_mile_default(auth_client: FlaskClient) -> None:
    """The default service distance is 2,000 miles, not the old 500 km."""
    v = mk_vehicle(auth_client)
    far = (date.today() + timedelta(days=200)).isoformat()  # well outside the 30-day window
    mk_service(auth_client, v["id"], category="Oil change",
               odometer=1000, odometer_unit="km",
               next_due_date=far, next_due_distance=5000)
    auth_client.post(f"/api/vehicles/{v['id']}/odometer", json={
        "date": "2025-06-01", "odometer": 2000, "unit": "km",
    })
    [r] = _vehicle_reminders(auth_client, v["id"])
    # 3,000 km to go: outside the old 500 km window, inside 2,000 mi (3,218 km).
    assert r["km_remaining"] == 3000.0
    assert r["status"] == "due_soon"


def test_reminder_window_honours_a_garage_override(
    garage_owner_client: FlaskClient, garage: dict
) -> None:
    """Widening the garage's window pulls a reminder forward to 'due_soon'."""
    v = mk_vehicle(garage_owner_client)
    soon = (date.today() + timedelta(days=80)).isoformat()
    mk_service(garage_owner_client, v["id"], category="Service", next_due_date=soon)
    assert _vehicle_reminders(garage_owner_client, v["id"])[0]["status"] == "upcoming"

    garage_owner_client.put(
        f"/api/garages/{garage['id']}/settings", json={"reminder_service_days": 120}
    )
    assert _vehicle_reminders(garage_owner_client, v["id"])[0]["status"] == "due_soon"


def test_reminder_distance_window_honours_a_garage_override(
    garage_owner_client: FlaskClient, garage: dict
) -> None:
    v = mk_vehicle(garage_owner_client)
    far = (date.today() + timedelta(days=200)).isoformat()
    mk_service(garage_owner_client, v["id"], category="Oil change",
               odometer=1000, odometer_unit="km",
               next_due_date=far, next_due_distance=2000)
    garage_owner_client.post(f"/api/vehicles/{v['id']}/odometer", json={
        "date": "2025-06-01", "odometer": 1800, "unit": "km",
    })
    # 200 km remaining is inside the 2,000-mile (3,218 km) default…
    assert _vehicle_reminders(garage_owner_client, v["id"])[0]["status"] == "due_soon"

    # …but outside a 100 km window.
    garage_owner_client.put(
        f"/api/garages/{garage['id']}/settings",
        json={"reminder_service_distance": 100, "reminder_service_unit": "km"},
    )
    assert _vehicle_reminders(garage_owner_client, v["id"])[0]["status"] == "upcoming"


def test_reminder_overdue_by_km(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    mk_service(auth_client, v["id"], category="Oil change",
               odometer=1000, odometer_unit="km", next_due_distance=2000)
    auth_client.post(f"/api/vehicles/{v['id']}/odometer", json={
        "date": "2025-06-01", "odometer": 2500, "unit": "km",
    })
    [r] = _vehicle_reminders(auth_client, v["id"])
    assert r["status"] == "overdue"
    assert r["km_remaining"] == -500.0


def test_reminder_due_soon_by_km(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    far = (date.today() + timedelta(days=200)).isoformat()
    mk_service(auth_client, v["id"], category="Oil change",
               odometer=1000, odometer_unit="km",
               next_due_date=far, next_due_distance=2000)
    auth_client.post(f"/api/vehicles/{v['id']}/odometer", json={
        "date": "2025-06-01", "odometer": 1800, "unit": "km",
    })
    [r] = _vehicle_reminders(auth_client, v["id"])
    assert r["status"] == "due_soon"
    assert r["km_remaining"] == 200.0


def test_reminder_superseded_by_newer_same_category(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    mk_service(auth_client, v["id"], date="2024-01-01", category="Service",
               next_due_date="2024-06-01")
    far = (date.today() + timedelta(days=300)).isoformat()
    mk_service(auth_client, v["id"], date="2025-01-01", category="Service",
               next_due_date=far)
    reminders = _vehicle_reminders(auth_client, v["id"])
    assert len(reminders) == 1
    assert reminders[0]["next_due_date"] == far


def test_reminder_not_superseded_by_other_category(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    mk_service(auth_client, v["id"], date="2024-01-01", category="Tyres",
               next_due_date="2024-06-01")
    mk_service(auth_client, v["id"], date="2025-01-01", category="Service")
    reminders = _vehicle_reminders(auth_client, v["id"])
    assert len(reminders) == 1
    assert reminders[0]["category"] == "Tyres"


def test_reminder_excludes_archived_vehicles(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    mk_service(auth_client, v["id"], category="Service", next_due_date="2020-01-01")
    auth_client.put(f"/api/vehicles/{v['id']}",
                    json={"name": v["name"], "archived": True})
    assert auth_client.get("/api/reminders").json == []


def test_reminders_sorted_most_urgent_first(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    far = (date.today() + timedelta(days=200)).isoformat()
    mk_service(auth_client, v["id"], category="Tyres", next_due_date=far)
    mk_service(auth_client, v["id"], category="Service", next_due_date="2020-01-01")
    statuses = [r["status"] for r in _vehicle_reminders(auth_client, v["id"])]
    assert statuses == ["overdue", "upcoming"]


# ── fault codes ──────────────────────────────────────────────────────────────

def test_create_with_fault_codes(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_service(auth_client, v["id"], fault_codes=["P0016", "U0100"])
    assert len(s["fault_codes"]) == 2
    assert s["fault_codes"][0]["code"] == "P0016"
    assert "description" in s["fault_codes"][0]
    assert s["fault_codes"][1]["code"] == "U0100"


def test_fault_codes_on_get(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_service(auth_client, v["id"], fault_codes=["P0300"])
    detail = auth_client.get(f"/api/services/{s['id']}").json
    assert len(detail["fault_codes"]) == 1
    assert detail["fault_codes"][0]["code"] == "P0300"
    assert "system" in detail["fault_codes"][0]


def test_fault_codes_on_list(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    mk_service(auth_client, v["id"], fault_codes=["P0016"])
    services = auth_client.get(f"/api/vehicles/{v['id']}/services").json
    assert services[0]["fault_codes"][0]["code"] == "P0016"
    all_services = auth_client.get("/api/services").json
    codes = [s for s in all_services if s["fault_codes"]]
    assert len(codes) >= 1


def test_update_fault_codes(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_service(auth_client, v["id"], fault_codes=["P0016"])
    r = auth_client.put(f"/api/services/{s['id']}", json={
        "date": s["date"], "title": s["title"], "fault_codes": ["P0300", "P0420"],
    })
    assert r.status_code == 200
    assert [fc["code"] for fc in r.json["fault_codes"]] == ["P0300", "P0420"]


def test_clear_fault_codes(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_service(auth_client, v["id"], fault_codes=["P0016"])
    r = auth_client.put(f"/api/services/{s['id']}", json={
        "date": s["date"], "title": s["title"], "fault_codes": [],
    })
    assert r.status_code == 200
    assert r.json["fault_codes"] == []


def test_fault_codes_unknown_code_no_description(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_service(auth_client, v["id"], fault_codes=["P1234"])
    fc = s["fault_codes"][0]
    assert fc["code"] == "P1234"
    assert "description" not in fc


def test_fault_codes_deleted_with_service(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_service(auth_client, v["id"], fault_codes=["P0016"])
    assert auth_client.delete(f"/api/services/{s['id']}").status_code == 204
    new_s = mk_service(auth_client, v["id"])
    assert new_s["fault_codes"] == []


def test_fault_codes_must_be_list(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    r = auth_client.post(f"/api/vehicles/{v['id']}/services", json={
        "date": "2025-01-01", "title": "x", "fault_codes": "P0016",
    })
    assert r.status_code == 400
    assert "list" in r.json["error"]
