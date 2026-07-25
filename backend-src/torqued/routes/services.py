from typing import Any

from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from torqued import analytics
from torqued.access import accessible_garage_ids, can_write, garage_role, vehicle_role
from torqued.db import get_db
from torqued.repositories.service_log_repository import ServiceLogRepository
from torqued.repositories.service_schedule_repository import ServiceScheduleRepository
from torqued.units import parse_distance

bp = Blueprint("services", __name__)


def _service_data(d: dict[str, Any]) -> dict[str, Any] | tuple[Response, int]:
    """Validate and normalise a service log payload; return data dict or an error response.

    Odometer and next-due distances arrive in the unit the user entered
    ('odometer' + 'odometer_unit', 'next_due_distance' in the same unit) and are
    stored canonically in km.
    """
    if not (d.get("date") or "").strip():
        return jsonify(error="date is required"), 400
    if not (d.get("title") or "").strip():
        return jsonify(error="title is required"), 400

    def opt(key: str) -> Any:
        v = d.get(key)
        return v if v not in ("", None) else None

    try:
        odometer_km, unit = parse_distance(d)
        next_due_km, _ = parse_distance(d, value_key="next_due_distance")
        cost = float(opt("cost")) if opt("cost") is not None else None
    except ValueError:
        return jsonify(error="odometer, next_due_distance, and cost must be numeric"), 400

    schedule_ids = d.get("service_schedule_ids")
    if schedule_ids is not None:
        if not isinstance(schedule_ids, list):
            return jsonify(error="service_schedule_ids must be a list"), 400
        try:
            schedule_ids = [int(s) for s in schedule_ids]
        except (TypeError, ValueError):
            return jsonify(error="service_schedule_ids must be integers"), 400

    # A service's next-due comes from either the schedule(s) it fulfils or a manual
    # next-due, never both — otherwise the same maintenance shows two reminders.
    if schedule_ids and (opt("next_due_date") is not None or next_due_km is not None):
        return jsonify(
            error="a service can fulfil schedules or set its own next-due, not both"
        ), 400

    fault_codes = d.get("fault_codes")
    if fault_codes is not None and not isinstance(fault_codes, list):
        return jsonify(error="fault_codes must be a list"), 400

    result: dict[str, Any] = {
        "date": d["date"].strip(),
        "title": d["title"].strip(),
        "category": opt("category"),
        "description": opt("description"),
        "performed_by": opt("performed_by"),
        "cost": cost,
        "odometer_km": odometer_km,
        "odometer_unit": unit if odometer_km is not None else None,
        "next_due_date": opt("next_due_date"),
        "next_due_km": next_due_km,
    }
    if schedule_ids is not None:
        result["service_schedule_ids"] = schedule_ids
    if fault_codes is not None:
        result["fault_codes"] = [str(c) for c in fault_codes]
    return result


def _check_schedule(
    db: Any, data: dict[str, Any], vehicle_id: int
) -> tuple[Response, int] | None:
    """Reject a payload whose service_schedule_ids don't all belong to `vehicle_id`."""
    schedule_ids = data.get("service_schedule_ids")
    if not schedule_ids:
        return None
    repo = ServiceScheduleRepository(db)
    for schedule_id in schedule_ids:
        schedule = repo.get_by_id(schedule_id)
        if schedule is None or schedule["vehicle_id"] != vehicle_id:
            return jsonify(error="a service schedule does not belong to this vehicle"), 400
    return None


def _check_log(
    db: Any, log: dict[str, Any] | None, write: bool = False
) -> tuple[Response, int] | None:
    """Return an error response if the log is missing/out of scope/read-only, else None."""
    role = garage_role(db, current_user, log["garage_id"]) if log else None
    if log is None or role is None:
        return jsonify(error="Not found"), 404
    if write and not can_write(role):
        return jsonify(error="Read-only access to this garage"), 403
    return None


@bp.get("/api/services")
@login_required
def list_services() -> ResponseReturnValue:
    garage_id_raw = request.args.get("garage_id")
    with get_db() as db:
        garage_ids = accessible_garage_ids(db, current_user)
        if garage_id_raw:
            try:
                garage_id = int(garage_id_raw)
            except ValueError:
                return jsonify(error="garage_id must be an integer"), 400
            if garage_id not in garage_ids:
                return jsonify(error="Not found"), 404
            garage_ids = [garage_id]
        return jsonify(ServiceLogRepository(db).list_for_garages(garage_ids))


@bp.get("/api/services/performers")
@login_required
def performers() -> Response:
    with get_db() as db:
        garage_ids = accessible_garage_ids(db, current_user)
        return jsonify(ServiceLogRepository(db).performers(garage_ids))


@bp.get("/api/vehicles/<int:vehicle_id>/services")
@login_required
def list_vehicle_services(vehicle_id: int) -> ResponseReturnValue:
    with get_db() as db:
        if vehicle_role(db, current_user, vehicle_id) is None:
            return jsonify(error="Not found"), 404
        return jsonify(ServiceLogRepository(db).list_for_vehicle(vehicle_id))


@bp.post("/api/vehicles/<int:vehicle_id>/services")
@login_required
def create_service(vehicle_id: int) -> ResponseReturnValue:
    data = _service_data(request.json or {})
    if isinstance(data, tuple):
        return data
    with get_db() as db:
        role = vehicle_role(db, current_user, vehicle_id)
        if role is None:
            return jsonify(error="Not found"), 404
        if not can_write(role):
            return jsonify(error="Read-only access to this garage"), 403
        err = _check_schedule(db, data, vehicle_id)
        if err:
            return err
        log = ServiceLogRepository(db).create(
            {**data, "vehicle_id": vehicle_id}, changed_by=current_user.id
        )
    analytics.capture(
        current_user.id,
        "service_log.created",
        {"service_log_id": log["id"], "vehicle_id": vehicle_id},
    )
    return jsonify(log), 201


@bp.get("/api/services/<int:log_id>")
@login_required
def get_service(log_id: int) -> ResponseReturnValue:
    with get_db() as db:
        log = ServiceLogRepository(db).get_by_id(log_id)
        err = _check_log(db, log)
        if err:
            return err
    return jsonify(log)


@bp.put("/api/services/<int:log_id>")
@login_required
def update_service(log_id: int) -> ResponseReturnValue:
    data = _service_data(request.json or {})
    if isinstance(data, tuple):
        return data
    with get_db() as db:
        repo = ServiceLogRepository(db)
        log = repo.get_by_id(log_id)
        err = _check_log(db, log, write=True)
        if err:
            return err
        assert log is not None  # _check_log returns a 404 response when the log is missing
        err = _check_schedule(db, data, log["vehicle_id"])
        if err:
            return err
        return jsonify(repo.update(log_id, data, changed_by=current_user.id))


@bp.delete("/api/services/<int:log_id>")
@login_required
def delete_service(log_id: int) -> ResponseReturnValue:
    with get_db() as db:
        repo = ServiceLogRepository(db)
        err = _check_log(db, repo.get_by_id(log_id), write=True)
        if err:
            return err
        repo.delete(log_id)
    return "", 204


@bp.get("/api/services/<int:log_id>/history")
@login_required
def service_history(log_id: int) -> ResponseReturnValue:
    with get_db() as db:
        repo = ServiceLogRepository(db)
        err = _check_log(db, repo.get_by_id(log_id))
        if err:
            return err
        return jsonify(repo.get_history(log_id))


@bp.post("/api/services/<int:log_id>/revert/<int:version_id>")
@login_required
def revert_service(log_id: int, version_id: int) -> ResponseReturnValue:
    with get_db() as db:
        repo = ServiceLogRepository(db)
        err = _check_log(db, repo.get_by_id(log_id), write=True)
        if err:
            return err
        log = repo.revert(log_id, version_id, changed_by=current_user.id)
    if not log:
        return jsonify(error="Version not found"), 404
    return jsonify(log)
