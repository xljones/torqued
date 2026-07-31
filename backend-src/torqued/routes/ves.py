from flask import Blueprint, jsonify
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from torqued import ves
from torqued.access import can_write, vehicle_role
from torqued.db import get_db
from torqued.repositories.vehicle_repository import VehicleRepository
from torqued.repositories.ves_repository import VesRepository

bp = Blueprint("ves", __name__)


@bp.get("/api/ves/status")
@login_required
def ves_status() -> ResponseReturnValue:
    return jsonify(configured=ves.is_configured()), 200


@bp.get("/api/vehicles/<int:vehicle_id>/ves")
@login_required
def get_ves(vehicle_id: int) -> ResponseReturnValue:
    """The stored DVLA VES snapshot (tax + MOT status + vehicle profile) for a vehicle."""
    with get_db() as db:
        if vehicle_role(db, current_user, vehicle_id) is None:
            return jsonify(error="Not found"), 404
        return jsonify(
            configured=ves.is_configured(),
            ves=VesRepository(db).get_for_vehicle(vehicle_id),
        ), 200


@bp.post("/api/vehicles/<int:vehicle_id>/ves/refresh")
@login_required
def refresh_ves(vehicle_id: int) -> ResponseReturnValue:
    with get_db() as db:
        role = vehicle_role(db, current_user, vehicle_id)
        if role is None:
            return jsonify(error="Not found"), 404
        if not can_write(role):
            return jsonify(error="Read-only access to this garage"), 403
        vehicle = VehicleRepository(db).get_by_id(vehicle_id)
        registration = (vehicle or {}).get("registration") or ""
        if not registration.strip():
            return jsonify(error="Vehicle has no registration set"), 400
    if not ves.is_configured():
        return jsonify(error="Vehicle enquiry lookups are disabled"), 503
    try:
        payload = ves.fetch_ves(registration)
    except ves.VesError as e:
        return jsonify(error=str(e)), e.status
    with get_db() as db:
        repo = VesRepository(db)
        repo.replace_for_vehicle(vehicle_id, payload)
        data = repo.get_for_vehicle(vehicle_id)
    return jsonify(configured=True, ves=data), 200
