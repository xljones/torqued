from typing import Any

from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from torqued import analytics
from torqued.access import can_write, garage_role, vehicle_role
from torqued.db import get_db
from torqued.domain.service_schedule import ScheduleKind
from torqued.repositories.service_schedule_repository import KINDS, ServiceScheduleRepository
from torqued.units import parse_distance

bp = Blueprint("schedules", __name__)


def _schedule_data(d: dict[str, Any]) -> dict[str, Any] | tuple[Response, int]:
    """Validate and normalise a schedule payload; return data dict or an error response.

    The distance interval arrives in the unit the user entered ('interval_distance' +
    'interval_unit') and is stored canonically in km. A schedule needs at least one of a
    month interval or a distance interval, and a 'custom' schedule needs a name.
    """
    kind = d.get("kind")
    if kind not in KINDS:
        return jsonify(error=f"kind must be one of {', '.join(KINDS)}"), 400

    def opt(key: str) -> Any:
        v = d.get(key)
        return v if v not in ("", None) else None

    try:
        raw_months = opt("interval_months")
        interval_months = int(raw_months) if raw_months is not None else None
        interval_km, _ = parse_distance(d, value_key="interval_distance", unit_key="interval_unit")
    except (TypeError, ValueError):
        return jsonify(error="interval_months and interval_distance must be numeric"), 400

    if interval_months is not None and interval_months <= 0:
        return jsonify(error="interval_months must be positive"), 400
    if interval_km is not None and interval_km <= 0:
        return jsonify(error="interval_distance must be positive"), 400
    if interval_months is None and interval_km is None:
        return jsonify(error="a schedule needs a month or distance interval"), 400

    name = opt("name")
    if kind == ScheduleKind.CUSTOM and not name:
        return jsonify(error="a custom schedule needs a name"), 400

    return {
        "kind": kind,
        "name": name,
        "interval_months": interval_months,
        "interval_km": interval_km,
        "enabled": 1 if d.get("enabled", True) else 0,
    }


def _check_schedule(
    db: Any, schedule: dict[str, Any] | None, write: bool = False
) -> tuple[Response, int] | None:
    """Return an error response if the schedule is missing/out of scope/read-only."""
    role = garage_role(db, current_user, schedule["garage_id"]) if schedule else None
    if schedule is None or role is None:
        return jsonify(error="Not found"), 404
    if write and not can_write(role):
        return jsonify(error="Read-only access to this garage"), 403
    return None


@bp.get("/api/vehicles/<int:vehicle_id>/schedules")
@login_required
def list_schedules(vehicle_id: int) -> ResponseReturnValue:
    with get_db() as db:
        if vehicle_role(db, current_user, vehicle_id) is None:
            return jsonify(error="Not found"), 404
        return jsonify(ServiceScheduleRepository(db).list_for_vehicle(vehicle_id))


@bp.post("/api/vehicles/<int:vehicle_id>/schedules")
@login_required
def create_schedule(vehicle_id: int) -> ResponseReturnValue:
    data = _schedule_data(request.json or {})
    if isinstance(data, tuple):
        return data
    with get_db() as db:
        role = vehicle_role(db, current_user, vehicle_id)
        if role is None:
            return jsonify(error="Not found"), 404
        if not can_write(role):
            return jsonify(error="Read-only access to this garage"), 403
        schedule = ServiceScheduleRepository(db).create({**data, "vehicle_id": vehicle_id})
    analytics.capture(
        current_user.id,
        "service_schedule.created",
        {"service_schedule_id": schedule["id"], "vehicle_id": vehicle_id, "kind": schedule["kind"]},
    )
    return jsonify(schedule), 201


@bp.put("/api/schedules/<int:schedule_id>")
@login_required
def update_schedule(schedule_id: int) -> ResponseReturnValue:
    data = _schedule_data(request.json or {})
    if isinstance(data, tuple):
        return data
    with get_db() as db:
        repo = ServiceScheduleRepository(db)
        err = _check_schedule(db, repo.get_by_id(schedule_id), write=True)
        if err:
            return err
        return jsonify(repo.update(schedule_id, data))


@bp.delete("/api/schedules/<int:schedule_id>")
@login_required
def delete_schedule(schedule_id: int) -> ResponseReturnValue:
    with get_db() as db:
        repo = ServiceScheduleRepository(db)
        err = _check_schedule(db, repo.get_by_id(schedule_id), write=True)
        if err:
            return err
        repo.delete(schedule_id)
    return "", 204
