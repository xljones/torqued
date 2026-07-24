from flask import Blueprint, jsonify
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from torqued import tax
from torqued.access import can_write, vehicle_role
from torqued.db import get_db
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
    with get_db() as db:
        repo = TaxRepository(db)
        repo.replace_for_vehicle(vehicle_id, payload)
        data = repo.get_for_vehicle(vehicle_id)
    return jsonify(configured=True, tax=data), 200
