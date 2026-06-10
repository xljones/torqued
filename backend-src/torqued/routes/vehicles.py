from typing import Any

from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from torqued.db import get_db
from torqued.repositories.service_log_repository import ServiceLogRepository
from torqued.repositories.vehicle_repository import VehicleRepository

bp = Blueprint("vehicles", __name__)

KINDS = ("car", "motorcycle")
ODOMETER_UNITS = ("mi", "km")


def _vehicle_data(d: dict[str, Any]) -> dict[str, Any] | tuple[Response, int]:
    """Validate and normalise a vehicle payload; return data dict or an error response."""
    if not (d.get("name") or "").strip():
        return jsonify(error="name is required"), 400
    kind = d.get("kind") or "car"
    if kind not in KINDS:
        return jsonify(error=f"kind must be one of {', '.join(KINDS)}"), 400
    unit = d.get("odometer_unit") or "mi"
    if unit not in ODOMETER_UNITS:
        return jsonify(error=f"odometer_unit must be one of {', '.join(ODOMETER_UNITS)}"), 400

    def opt(key: str) -> Any:
        v = d.get(key)
        return v if v not in ("", None) else None

    def num(key: str) -> float | None:
        v = opt(key)
        return float(v) if v is not None else None

    try:
        year = int(opt("year")) if opt("year") is not None else None
        front = num("tyre_pressure_front_psi")
        rear = num("tyre_pressure_rear_psi")
    except (TypeError, ValueError):
        return jsonify(error="year and tyre pressures must be numeric"), 400

    return {
        "name": d["name"].strip(),
        "kind": kind,
        "make": opt("make"),
        "model": opt("model"),
        "year": year,
        "registration": opt("registration"),
        "vin": opt("vin"),
        "colour": opt("colour"),
        "fuel_type": opt("fuel_type"),
        "odometer_unit": unit,
        "purchase_date": opt("purchase_date"),
        "tyre_size_front": opt("tyre_size_front"),
        "tyre_size_rear": opt("tyre_size_rear"),
        "tyre_pressure_front_psi": front,
        "tyre_pressure_rear_psi": rear,
        "notes": opt("notes"),
        "archived": 1 if d.get("archived") else 0,
    }


@bp.get("/api/vehicles")
@login_required
def list_vehicles() -> Response:
    include_archived = request.args.get("archived") == "1"
    with get_db() as db:
        return jsonify(VehicleRepository(db).list_all(include_archived=include_archived))


@bp.post("/api/vehicles")
@login_required
def create_vehicle() -> ResponseReturnValue:
    data = _vehicle_data(request.json or {})
    if isinstance(data, tuple):
        return data
    with get_db() as db:
        vehicle = VehicleRepository(db).create(data, changed_by=current_user.id)
    return jsonify(vehicle), 201


@bp.get("/api/vehicles/<int:vehicle_id>")
@login_required
def get_vehicle(vehicle_id: int) -> ResponseReturnValue:
    with get_db() as db:
        vehicle = VehicleRepository(db).get_detail(vehicle_id)
        if not vehicle:
            return jsonify(error="Not found"), 404
        vehicle["reminders"] = ServiceLogRepository(db).reminders(vehicle_id)
    return jsonify(vehicle)


@bp.put("/api/vehicles/<int:vehicle_id>")
@login_required
def update_vehicle(vehicle_id: int) -> ResponseReturnValue:
    data = _vehicle_data(request.json or {})
    if isinstance(data, tuple):
        return data
    with get_db() as db:
        repo = VehicleRepository(db)
        if not repo.get_by_id(vehicle_id):
            return jsonify(error="Not found"), 404
        return jsonify(repo.update(vehicle_id, data, changed_by=current_user.id))


@bp.delete("/api/vehicles/<int:vehicle_id>")
@login_required
def delete_vehicle(vehicle_id: int) -> ResponseReturnValue:
    with get_db() as db:
        if not VehicleRepository(db).delete(vehicle_id):
            return jsonify(error="Not found"), 404
    return "", 204


@bp.put("/api/vehicles/<int:vehicle_id>/specs")
@login_required
def replace_specs(vehicle_id: int) -> ResponseReturnValue:
    d = request.json or {}
    specs = d.get("specs")
    if not isinstance(specs, list):
        return jsonify(error="specs must be a list"), 400
    for spec in specs:
        if not isinstance(spec, dict) or not (spec.get("name") or "").strip():
            return jsonify(error="each spec needs a name"), 400
        spec["name"] = spec["name"].strip()
        spec["value"] = (spec.get("value") or "").strip()
    with get_db() as db:
        repo = VehicleRepository(db)
        if not repo.get_by_id(vehicle_id):
            return jsonify(error="Not found"), 404
        return jsonify(repo.replace_specs(vehicle_id, specs))


@bp.get("/api/vehicles/<int:vehicle_id>/mileage")
@login_required
def mileage_series(vehicle_id: int) -> ResponseReturnValue:
    with get_db() as db:
        repo = VehicleRepository(db)
        if not repo.get_by_id(vehicle_id):
            return jsonify(error="Not found"), 404
        return jsonify(repo.mileage_series(vehicle_id))


@bp.get("/api/vehicles/<int:vehicle_id>/history")
@login_required
def vehicle_history(vehicle_id: int) -> Response:
    with get_db() as db:
        return jsonify(VehicleRepository(db).get_history(vehicle_id))


@bp.post("/api/vehicles/<int:vehicle_id>/revert/<int:version_id>")
@login_required
def revert_vehicle(vehicle_id: int, version_id: int) -> ResponseReturnValue:
    with get_db() as db:
        vehicle = VehicleRepository(db).revert(vehicle_id, version_id, changed_by=current_user.id)
    if not vehicle:
        return jsonify(error="Version not found"), 404
    return jsonify(vehicle)


@bp.get("/api/reminders")
@login_required
def all_reminders() -> Response:
    with get_db() as db:
        return jsonify(ServiceLogRepository(db).reminders())
