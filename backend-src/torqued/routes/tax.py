from flask import Blueprint, jsonify
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from torqued import tax
from torqued.access import can_write, vehicle_role
from torqued.db import get_db
from torqued.repositories.mot_status_repository import MotStatusRepository
from torqued.repositories.tax_repository import TaxRepository
from torqued.repositories.vehicle_repository import VehicleRepository

bp = Blueprint("tax", __name__)


@bp.get("/api/tax/status")
@login_required
def tax_status() -> ResponseReturnValue:
    return jsonify(configured=tax.is_configured()), 200


@bp.get("/api/vehicles/<int:vehicle_id>/tax")
@login_required
def get_tax(vehicle_id: int) -> ResponseReturnValue:
    with get_db() as db:
        if vehicle_role(db, current_user, vehicle_id) is None:
            return jsonify(error="Not found"), 404
        return jsonify(
            configured=tax.is_configured(),
            tax=TaxRepository(db).get_for_vehicle(vehicle_id),
        ), 200


@bp.get("/api/vehicles/<int:vehicle_id>/mot-status")
@login_required
def get_mot_status(vehicle_id: int) -> ResponseReturnValue:
    """The DVLA VES current-MOT-status snapshot (status + expiry) for a vehicle.

    Separate from ``/mot`` (the DVSA test history); the MOT card reads both and shows the
    later expiry. Fetched from the same VES source as tax, hence this blueprint.
    """
    with get_db() as db:
        if vehicle_role(db, current_user, vehicle_id) is None:
            return jsonify(error="Not found"), 404
        return jsonify(
            configured=tax.is_configured(),
            mot_status=MotStatusRepository(db).get_for_vehicle(vehicle_id),
        ), 200


@bp.post("/api/vehicles/<int:vehicle_id>/tax/refresh")
@login_required
def refresh_tax(vehicle_id: int) -> ResponseReturnValue:
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
    if not tax.is_configured():
        return jsonify(error="Tax lookups are disabled"), 503
    try:
        payload = tax.fetch_tax(registration)
    except tax.TaxError as e:
        return jsonify(error=str(e)), e.status
    # One VES fetch carries both tax and MOT status; persist each as its own record.
    with get_db() as db:
        tax_repo = TaxRepository(db)
        mot_repo = MotStatusRepository(db)
        tax_repo.replace_for_vehicle(vehicle_id, payload)
        mot_repo.replace_for_vehicle(vehicle_id, payload)
        tax_data = tax_repo.get_for_vehicle(vehicle_id)
        mot_status_data = mot_repo.get_for_vehicle(vehicle_id)
    return jsonify(configured=True, tax=tax_data, mot_status=mot_status_data), 200
