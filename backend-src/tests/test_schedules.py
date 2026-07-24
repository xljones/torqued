"""Tests for /api/schedules: CRUD, validation, access control, and reminder projection."""
from datetime import date, timedelta
from typing import Any

from flask.testing import FlaskClient

from tests.test_services import mk_service
from tests.test_vehicles import mk_vehicle
from torqued.units import from_km


def mk_schedule(client: FlaskClient, vehicle_id: int, **overrides) -> dict:
    body = {"kind": "minor", "interval_months": 12, **overrides}
    r = client.post(f"/api/vehicles/{vehicle_id}/schedules", json=body)
    assert r.status_code == 201, r.json
    return r.json


def _seed_vehicle_and_schedule(garage: dict[str, Any]) -> tuple[dict, dict]:
    """Create a vehicle + schedule directly (for readonly tests, which can't write)."""
    from torqued.db import get_db
    from torqued.repositories.service_schedule_repository import ServiceScheduleRepository
    from torqued.repositories.vehicle_repository import VehicleRepository

    with get_db() as db:
        vehicle = VehicleRepository(db).create(garage["id"], {"name": "Shared bike"})
        schedule = ServiceScheduleRepository(db).create(
            {"vehicle_id": vehicle["id"], "kind": "minor", "interval_months": 12}
        )
    return vehicle, schedule


# ── create ────────────────────────────────────────────────────────────────────

def test_create_minor(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_schedule(auth_client, v["id"], interval_months=6)
    assert s["kind"] == "minor"
    assert s["interval_months"] == 6
    assert s["interval_km"] is None
    assert s["enabled"] == 1


def test_create_converts_distance_to_km(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_schedule(auth_client, v["id"], kind="major", interval_months=None,
                    interval_distance=1000, interval_unit="mi")
    assert s["interval_km"] == 1609.344


def test_create_custom_needs_name(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    r = auth_client.post(f"/api/vehicles/{v['id']}/schedules",
                         json={"kind": "custom", "interval_months": 12})
    assert r.status_code == 400
    s = mk_schedule(auth_client, v["id"], kind="custom", name="Valve check")
    assert s["name"] == "Valve check"


def test_create_rejects_bad_kind(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    r = auth_client.post(f"/api/vehicles/{v['id']}/schedules",
                         json={"kind": "annual", "interval_months": 12})
    assert r.status_code == 400


def test_create_rejects_non_numeric_interval(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    r = auth_client.post(f"/api/vehicles/{v['id']}/schedules",
                         json={"kind": "minor", "interval_months": "soon"})
    assert r.status_code == 400


def test_create_rejects_non_positive_intervals(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    assert auth_client.post(f"/api/vehicles/{v['id']}/schedules",
                            json={"kind": "minor", "interval_months": 0}).status_code == 400
    assert auth_client.post(f"/api/vehicles/{v['id']}/schedules",
                            json={"kind": "minor", "interval_distance": -5,
                                  "interval_unit": "km"}).status_code == 400


def test_create_requires_an_interval(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    r = auth_client.post(f"/api/vehicles/{v['id']}/schedules", json={"kind": "minor"})
    assert r.status_code == 400


def test_create_vehicle_404(auth_client: FlaskClient) -> None:
    r = auth_client.post("/api/vehicles/999/schedules",
                         json={"kind": "minor", "interval_months": 12})
    assert r.status_code == 404


def test_create_readonly_403(readonly_client: FlaskClient, garage: dict[str, Any]) -> None:
    v, _ = _seed_vehicle_and_schedule(garage)
    r = readonly_client.post(f"/api/vehicles/{v['id']}/schedules",
                             json={"kind": "minor", "interval_months": 12})
    assert r.status_code == 403


# ── list ──────────────────────────────────────────────────────────────────────

def test_list_ordered_and_scoped(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    mk_schedule(auth_client, v["id"], kind="minor", interval_months=6)
    mk_schedule(auth_client, v["id"], kind="major", interval_months=24)
    listed = auth_client.get(f"/api/vehicles/{v['id']}/schedules").json
    assert [s["kind"] for s in listed] == ["major", "minor"]


def test_list_vehicle_404(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/vehicles/999/schedules").status_code == 404


# ── update ──────────────────────────────────────────────────────────────────

def test_update(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_schedule(auth_client, v["id"], interval_months=12)
    r = auth_client.put(f"/api/schedules/{s['id']}",
                        json={"kind": "minor", "interval_months": 18, "enabled": False})
    assert r.status_code == 200
    assert r.json["interval_months"] == 18
    assert r.json["enabled"] == 0


def test_update_validation(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_schedule(auth_client, v["id"])
    r = auth_client.put(f"/api/schedules/{s['id']}", json={"kind": "minor"})
    assert r.status_code == 400


def test_update_404(auth_client: FlaskClient) -> None:
    r = auth_client.put("/api/schedules/999", json={"kind": "minor", "interval_months": 12})
    assert r.status_code == 404


def test_update_readonly_403(readonly_client: FlaskClient, garage: dict[str, Any]) -> None:
    _, s = _seed_vehicle_and_schedule(garage)
    r = readonly_client.put(f"/api/schedules/{s['id']}",
                            json={"kind": "minor", "interval_months": 6})
    assert r.status_code == 403


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_schedule(auth_client, v["id"])
    assert auth_client.delete(f"/api/schedules/{s['id']}").status_code == 204
    assert auth_client.get(f"/api/vehicles/{v['id']}/schedules").json == []


def test_delete_removes_link_keeps_service(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_schedule(auth_client, v["id"])
    log = mk_service(auth_client, v["id"], service_schedule_ids=[s["id"]])
    assert log["service_schedule_ids"] == [s["id"]]
    auth_client.delete(f"/api/schedules/{s['id']}")
    # The service log survives; only its (now-dangling) link is gone.
    assert auth_client.get(f"/api/services/{log['id']}").json["service_schedule_ids"] == []


def test_delete_404(auth_client: FlaskClient) -> None:
    assert auth_client.delete("/api/schedules/999").status_code == 404


def test_delete_readonly_403(readonly_client: FlaskClient, garage: dict[str, Any]) -> None:
    _, s = _seed_vehicle_and_schedule(garage)
    assert readonly_client.delete(f"/api/schedules/{s['id']}").status_code == 403


# ── service-log linkage (many-to-many) ──────────────────────────────────────

def test_service_links_multiple_schedules(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    minor = mk_schedule(auth_client, v["id"], kind="minor", interval_months=6)
    major = mk_schedule(auth_client, v["id"], kind="major", interval_months=24)
    log = mk_service(auth_client, v["id"], service_schedule_ids=[minor["id"], major["id"]])
    assert sorted(log["service_schedule_ids"]) == sorted([minor["id"], major["id"]])


def test_service_dedupes_repeated_schedule(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_schedule(auth_client, v["id"])
    log = mk_service(auth_client, v["id"], service_schedule_ids=[s["id"], s["id"]])
    assert log["service_schedule_ids"] == [s["id"]]


def test_service_rejects_foreign_schedule(auth_client: FlaskClient) -> None:
    v1 = mk_vehicle(auth_client, name="Bike")
    v2 = mk_vehicle(auth_client, name="Car", kind="car")
    s = mk_schedule(auth_client, v1["id"])
    r = auth_client.post(
        f"/api/vehicles/{v2['id']}/services",
        json={"date": "2025-01-01", "title": "x", "service_schedule_ids": [s["id"]]},
    )
    assert r.status_code == 400


def test_service_rejects_unknown_schedule(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    r = auth_client.post(f"/api/vehicles/{v['id']}/services",
                         json={"date": "2025-01-01", "title": "x", "service_schedule_ids": [999]})
    assert r.status_code == 400


def test_service_rejects_non_integer_schedule(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    r = auth_client.post(f"/api/vehicles/{v['id']}/services",
                         json={"date": "2025-01-01", "title": "x", "service_schedule_ids": ["abc"]})
    assert r.status_code == 400


def test_service_rejects_non_list_schedules(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    r = auth_client.post(f"/api/vehicles/{v['id']}/services",
                         json={"date": "2025-01-01", "title": "x", "service_schedule_ids": 5})
    assert r.status_code == 400


def test_service_update_sets_and_clears_schedules(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_schedule(auth_client, v["id"])
    log = mk_service(auth_client, v["id"])
    r = auth_client.put(f"/api/services/{log['id']}",
                        json={"date": log["date"], "title": log["title"],
                              "service_schedule_ids": [s["id"]]})
    assert r.status_code == 200
    assert r.json["service_schedule_ids"] == [s["id"]]
    # An empty list clears the links.
    r = auth_client.put(f"/api/services/{log['id']}",
                        json={"date": log["date"], "title": log["title"],
                              "service_schedule_ids": []})
    assert r.json["service_schedule_ids"] == []


def test_service_update_rejects_foreign_schedule(auth_client: FlaskClient) -> None:
    v1 = mk_vehicle(auth_client, name="Bike")
    v2 = mk_vehicle(auth_client, name="Car", kind="car")
    s = mk_schedule(auth_client, v2["id"])
    log = mk_service(auth_client, v1["id"])
    r = auth_client.put(f"/api/services/{log['id']}",
                        json={"date": log["date"], "title": log["title"],
                              "service_schedule_ids": [s["id"]]})
    assert r.status_code == 400


# ── reminders ─────────────────────────────────────────────────────────────────

def _schedule_reminders(client: FlaskClient, vehicle_id: int) -> list[dict]:
    return [
        r for r in client.get(f"/api/vehicles/{vehicle_id}").json["reminders"]
        if r["type"] == "schedule"
    ]


def test_reminder_overdue_by_date(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_schedule(auth_client, v["id"], interval_months=12)
    mk_service(auth_client, v["id"], date="2020-01-01", service_schedule_ids=[s["id"]])
    [r] = _schedule_reminders(auth_client, v["id"])
    assert r["status"] == "overdue"
    assert r["title"] == "Minor service"
    assert r["next_due_date"] == "2021-01-01"


def test_reminder_due_soon_by_date(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    anchor = (date.today() + timedelta(days=10) - timedelta(days=365)).isoformat()
    s = mk_schedule(auth_client, v["id"], interval_months=12)
    mk_service(auth_client, v["id"], date=anchor, service_schedule_ids=[s["id"]])
    [r] = _schedule_reminders(auth_client, v["id"])
    assert r["status"] == "due_soon"


def test_reminder_upcoming(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_schedule(auth_client, v["id"], interval_months=12)
    mk_service(auth_client, v["id"], date=date.today().isoformat(), service_schedule_ids=[s["id"]])
    [r] = _schedule_reminders(auth_client, v["id"])
    assert r["status"] == "upcoming"


def test_reminder_overdue_by_km(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_schedule(auth_client, v["id"], kind="major", interval_months=None,
                    interval_distance=2000, interval_unit="km")
    mk_service(auth_client, v["id"], date=date.today().isoformat(),
               odometer=1000, odometer_unit="km", service_schedule_ids=[s["id"]])
    auth_client.post(f"/api/vehicles/{v['id']}/odometer",
                     json={"date": date.today().isoformat(), "odometer": 3500, "unit": "km"})
    [r] = _schedule_reminders(auth_client, v["id"])
    assert r["status"] == "overdue"
    assert r["km_remaining"] == -500.0
    assert r["next_due_km"] == 3000.0


def test_reminder_due_soon_by_km(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_schedule(auth_client, v["id"], kind="major", interval_months=None,
                    interval_distance=2000, interval_unit="km")
    mk_service(auth_client, v["id"], date=date.today().isoformat(),
               odometer=1000, odometer_unit="km", service_schedule_ids=[s["id"]])
    auth_client.post(f"/api/vehicles/{v['id']}/odometer",
                     json={"date": date.today().isoformat(), "odometer": 2800, "unit": "km"})
    [r] = _schedule_reminders(auth_client, v["id"])
    assert r["status"] == "due_soon"
    assert r["km_remaining"] == 200.0


def test_reminder_absent_without_fulfilling_log(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    mk_schedule(auth_client, v["id"], interval_months=12)
    assert _schedule_reminders(auth_client, v["id"]) == []


def test_reminder_absent_when_km_interval_but_no_odometer(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_schedule(auth_client, v["id"], kind="major", interval_months=None,
                    interval_distance=2000, interval_unit="km")
    mk_service(auth_client, v["id"], date="2025-01-01", service_schedule_ids=[s["id"]])
    assert _schedule_reminders(auth_client, v["id"]) == []


def test_reminder_absent_when_disabled(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_schedule(auth_client, v["id"], interval_months=12, enabled=False)
    mk_service(auth_client, v["id"], date="2020-01-01", service_schedule_ids=[s["id"]])
    assert _schedule_reminders(auth_client, v["id"]) == []


def test_reminder_projects_from_newest_fulfilling_log(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_schedule(auth_client, v["id"], interval_months=12)
    mk_service(auth_client, v["id"], date="2020-01-01", service_schedule_ids=[s["id"]])
    mk_service(auth_client, v["id"], date="2024-06-15", service_schedule_ids=[s["id"]])
    [r] = _schedule_reminders(auth_client, v["id"])
    assert r["date"] == "2024-06-15"
    assert r["next_due_date"] == "2025-06-15"


def test_reminder_major_service_resets_both_minor_and_major(auth_client: FlaskClient) -> None:
    # A major service includes the minor work, so one log fulfils both schedules and
    # anchors both reminders — the minor doesn't immediately show as overdue.
    v = mk_vehicle(auth_client)
    minor = mk_schedule(auth_client, v["id"], kind="minor", interval_months=6)
    major = mk_schedule(auth_client, v["id"], kind="major", interval_months=24)
    mk_service(auth_client, v["id"], date="2024-01-01",
               service_schedule_ids=[minor["id"], major["id"]])
    reminders = {r["title"]: r for r in _schedule_reminders(auth_client, v["id"])}
    assert reminders["Minor service"]["next_due_date"] == "2024-07-01"
    assert reminders["Major service"]["next_due_date"] == "2026-01-01"


def test_reminder_projects_date_and_mileage_together(auth_client: FlaskClient) -> None:
    # A minor schedule due every 12 months OR every 10,000 mi.
    v = mk_vehicle(auth_client)  # vehicle odometer unit defaults to 'mi'
    s = mk_schedule(auth_client, v["id"], kind="minor", interval_months=12,
                    interval_distance=10000, interval_unit="mi")
    # Fulfilled on 2000-09-11 at 56,000 mi.
    mk_service(auth_client, v["id"], date="2000-09-11",
               odometer=56000, odometer_unit="mi", service_schedule_ids=[s["id"]])
    [r] = _schedule_reminders(auth_client, v["id"])
    # Next due exactly one year later, or 10,000 mi further on (66,000 mi).
    assert r["next_due_date"] == "2001-09-11"
    assert round(from_km(r["next_due_km"], "mi")) == 66000


def test_reminder_excludes_archived(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    s = mk_schedule(auth_client, v["id"], interval_months=12)
    mk_service(auth_client, v["id"], date="2020-01-01", service_schedule_ids=[s["id"]])
    auth_client.put(f"/api/vehicles/{v['id']}", json={"name": v["name"], "archived": True})
    assert auth_client.get("/api/reminders").json == []


# ── repository units (branches not reachable through routes) ─────────────────

def test_repository_units(app) -> None:
    from torqued.db import get_db
    from torqued.repositories.garage_repository import GarageRepository
    from torqued.repositories.service_schedule_repository import (
        ServiceScheduleRepository,
        add_months,
        schedule_title,
    )

    # add_months clamps to the shorter month's last day.
    assert add_months("2025-01-31", 1) == "2025-02-28"
    assert add_months("2025-11-15", 3) == "2026-02-15"

    # schedule_title falls back to a kind label, or a generic word for an un-named custom.
    assert schedule_title({"kind": "major", "name": None}) == "Major service"
    assert schedule_title({"kind": "custom", "name": None}) == "Service"
    assert schedule_title({"kind": "custom", "name": "Brakes"}) == "Brakes"

    with get_db() as db:
        repo = ServiceScheduleRepository(db)
        assert repo.reminders([]) == []
        # Called standalone (no injected `latest`), it fetches the odometer map itself —
        # the orchestrator normally passes its own to avoid the repeat scan.
        garage = GarageRepository(db).create("Schedule Repo Garage")
        assert repo.reminders([garage["id"]]) == []
        assert repo.get_by_id(999) is None
        assert repo.update(999, {"interval_months": 6}) is None
        assert repo.delete(999) is False
