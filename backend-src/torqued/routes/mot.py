from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from torqued import mot
from torqued.access import admin_required, can_write, vehicle_role
from torqued.db import get_db
from torqued.repositories.mot_repository import MotRepository
from torqued.repositories.vehicle_repository import VehicleRepository

bp = Blueprint("mot", __name__)


@bp.get("/api/dvsa-vehicles")
@admin_required
def dvsa_vehicles() -> ResponseReturnValue:
    """List every stored DVSA snapshot (site-admin only), newest refresh first, paginated."""
    page = max(1, request.args.get("page", 1, type=int))
    with get_db() as db:
        return jsonify(MotRepository(db).list_all(page)), 200


@bp.post("/api/dvsa-vehicles")
@admin_required
def create_dvsa_lookup() -> ResponseReturnValue:
    """Look up any registration at the DVSA and persist it, unassigned (site-admin).

    The record is stored detached (no vehicle); adding a garage vehicle on this plate
    later relinks it. Unconfigured → 503; unknown plate → 404 relayed from DVSA.
    """
    registration = ((request.json or {}).get("registration") or "").strip()
    if not registration:
        return jsonify(error="registration is required"), 400
    if not mot.is_configured():
        return jsonify(error="DVSA MOT API credentials are not configured"), 503
    try:
        payload = mot.fetch_vehicle(registration)
    except mot.MotError as e:
        return jsonify(error=str(e)), e.status
    with get_db() as db:
        MotRepository(db).store_detached_lookup(payload)
    return jsonify(
        registration=payload.get("registration"),
        make=payload.get("make"),
        model=payload.get("model"),
    ), 201


@bp.get("/api/dvsa-vehicles/<int:dvsa_id>/records")
@admin_required
def dvsa_vehicle_records(dvsa_id: int) -> ResponseReturnValue:
    """Return every raw DVSA record for one stored snapshot (site-admin only)."""
    with get_db() as db:
        records = MotRepository(db).get_records_by_id(dvsa_id)
    if records is None:
        return jsonify(error="Not found"), 404
    return jsonify(records), 200


@bp.get("/api/mot/status")
@login_required
def mot_status() -> ResponseReturnValue:
    return jsonify(configured=mot.is_configured()), 200


@bp.get("/api/mot/lookup/<registration>")
@login_required
def lookup_mot(registration: str) -> ResponseReturnValue:
    """Preview the DVSA record for a registration without storing anything.

    Used by the vehicle form to prefill identity fields before a vehicle exists.
    """
    if not mot.is_configured():
        return jsonify(error="DVSA MOT API credentials are not configured"), 503
    try:
        payload = mot.fetch_vehicle(registration)
    except mot.MotError as e:
        return jsonify(error=str(e)), e.status
    return jsonify(configured=True, mot_baseline=mot.to_baseline(payload)), 200


@bp.get("/api/vehicles/<int:vehicle_id>/mot")
@login_required
def get_mot(vehicle_id: int) -> ResponseReturnValue:
    with get_db() as db:
        if vehicle_role(db, current_user, vehicle_id) is None:
            return jsonify(error="Not found"), 404
        return jsonify(
            configured=mot.is_configured(),
            mot=MotRepository(db).get_for_vehicle(vehicle_id),
        ), 200


@bp.post("/api/vehicles/<int:vehicle_id>/mot/refresh")
@login_required
def refresh_mot(vehicle_id: int) -> ResponseReturnValue:
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
    if not mot.is_configured():
        return jsonify(error="DVSA MOT API credentials are not configured"), 503
    try:
        payload = mot.fetch_vehicle(registration)
    except mot.MotError as e:
        return jsonify(error=str(e)), e.status
    with get_db() as db:
        repo = MotRepository(db)
        repo.replace_for_vehicle(vehicle_id, payload)
        data = repo.get_for_vehicle(vehicle_id)
    return jsonify(configured=True, mot=data), 200
