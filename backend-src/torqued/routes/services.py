from typing import Any

from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from torqued.db import get_db
from torqued.repositories.service_log_repository import ServiceLogRepository
from torqued.repositories.vehicle_repository import VehicleRepository
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

    return {
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


@bp.get("/api/services")
@login_required
def list_services() -> Response:
    with get_db() as db:
        return jsonify(ServiceLogRepository(db).list_all())


@bp.get("/api/services/performers")
@login_required
def performers() -> Response:
    with get_db() as db:
        return jsonify(ServiceLogRepository(db).performers())


@bp.get("/api/vehicles/<int:vehicle_id>/services")
@login_required
def list_vehicle_services(vehicle_id: int) -> ResponseReturnValue:
    with get_db() as db:
        if not VehicleRepository(db).get_by_id(vehicle_id):
            return jsonify(error="Not found"), 404
        return jsonify(ServiceLogRepository(db).list_for_vehicle(vehicle_id))


@bp.post("/api/vehicles/<int:vehicle_id>/services")
@login_required
def create_service(vehicle_id: int) -> ResponseReturnValue:
    data = _service_data(request.json or {})
    if isinstance(data, tuple):
        return data
    with get_db() as db:
        if not VehicleRepository(db).get_by_id(vehicle_id):
            return jsonify(error="Not found"), 404
        log = ServiceLogRepository(db).create(
            {**data, "vehicle_id": vehicle_id}, changed_by=current_user.id
        )
    return jsonify(log), 201


@bp.get("/api/services/<int:log_id>")
@login_required
def get_service(log_id: int) -> ResponseReturnValue:
    with get_db() as db:
        log = ServiceLogRepository(db).get_by_id(log_id)
    if not log:
        return jsonify(error="Not found"), 404
    return jsonify(log)


@bp.put("/api/services/<int:log_id>")
@login_required
def update_service(log_id: int) -> ResponseReturnValue:
    data = _service_data(request.json or {})
    if isinstance(data, tuple):
        return data
    with get_db() as db:
        repo = ServiceLogRepository(db)
        if not repo.get_by_id(log_id):
            return jsonify(error="Not found"), 404
        return jsonify(repo.update(log_id, data, changed_by=current_user.id))


@bp.delete("/api/services/<int:log_id>")
@login_required
def delete_service(log_id: int) -> ResponseReturnValue:
    with get_db() as db:
        if not ServiceLogRepository(db).delete(log_id):
            return jsonify(error="Not found"), 404
    return "", 204


@bp.get("/api/services/<int:log_id>/history")
@login_required
def service_history(log_id: int) -> Response:
    with get_db() as db:
        return jsonify(ServiceLogRepository(db).get_history(log_id))


@bp.post("/api/services/<int:log_id>/revert/<int:version_id>")
@login_required
def revert_service(log_id: int, version_id: int) -> ResponseReturnValue:
    with get_db() as db:
        log = ServiceLogRepository(db).revert(log_id, version_id, changed_by=current_user.id)
    if not log:
        return jsonify(error="Version not found"), 404
    return jsonify(log)
