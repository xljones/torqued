from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from torqued.access import can_write, vehicle_role
from torqued.db import get_db
from torqued.repositories.odometer_log_repository import OdometerLogRepository
from torqued.units import parse_distance

bp = Blueprint("odometer", __name__)


@bp.get("/api/vehicles/<int:vehicle_id>/odometer")
@login_required
def list_odometer(vehicle_id: int) -> ResponseReturnValue:
    with get_db() as db:
        if vehicle_role(db, current_user, vehicle_id) is None:
            return jsonify(error="Not found"), 404
        return jsonify(OdometerLogRepository(db).list_for_vehicle(vehicle_id))


@bp.post("/api/vehicles/<int:vehicle_id>/odometer")
@login_required
def create_odometer(vehicle_id: int) -> ResponseReturnValue:
    d = request.json or {}
    if not (d.get("date") or "").strip():
        return jsonify(error="date is required"), 400
    try:
        odometer_km, unit = parse_distance(d, value_key="odometer", unit_key="unit")
    except ValueError:
        return jsonify(error="odometer must be numeric and unit must be mi or km"), 400
    if odometer_km is None:
        return jsonify(error="odometer is required"), 400
    with get_db() as db:
        role = vehicle_role(db, current_user, vehicle_id)
        if role is None:
            return jsonify(error="Not found"), 404
        if not can_write(role):
            return jsonify(error="Read-only access to this garage"), 403
        log = OdometerLogRepository(db).create(
            vehicle_id, d["date"].strip(), odometer_km, unit, note=d.get("note") or None
        )
    return jsonify(log), 201


@bp.delete("/api/odometer/<int:log_id>")
@login_required
def delete_odometer(log_id: int) -> ResponseReturnValue:
    with get_db() as db:
        repo = OdometerLogRepository(db)
        log = repo.get_by_id(log_id)
        role = vehicle_role(db, current_user, log["vehicle_id"]) if log else None
        if log is None or role is None:
            return jsonify(error="Not found"), 404
        if not can_write(role):
            return jsonify(error="Read-only access to this garage"), 403
        repo.delete(log_id)
    return "", 204
