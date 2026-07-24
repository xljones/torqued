from typing import Any

from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from torqued import analytics, mot
from torqued.access import accessible_garage_ids, can_write, garage_role, vehicle_role
from torqued.db import get_db
from torqued.repositories.mot_repository import MotRepository
from torqued.repositories.service_log_repository import ServiceLogRepository
from torqued.repositories.tax_repository import TaxRepository
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
        "engine_size": opt("engine_size"),
        "first_used_date": opt("first_used_date"),
        "registration_date": opt("registration_date"),
    }


def _check_vehicle(db: Any, vehicle_id: int, write: bool = False) -> tuple[Response, int] | None:
    """Return an error response if the vehicle is out of scope or read-only, else None."""
    role = vehicle_role(db, current_user, vehicle_id)
    if role is None:
        return jsonify(error="Not found"), 404
    if write and not can_write(role):
        return jsonify(error="Read-only access to this garage"), 403
    return None


@bp.get("/api/vehicles")
@login_required
def list_vehicles() -> ResponseReturnValue:
    include_archived = request.args.get("archived") == "1"
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
        return jsonify(
            VehicleRepository(db).list_for_garages(garage_ids, include_archived=include_archived)
        )


@bp.post("/api/vehicles")
@login_required
def create_vehicle() -> ResponseReturnValue:
    d = request.json or {}
    try:
        garage_id = int(d.get("garage_id") or "")
    except ValueError:
        return jsonify(error="garage_id is required"), 400
    data = _vehicle_data(d)
    if isinstance(data, tuple):
        return data
    with get_db() as db:
        role = garage_role(db, current_user, garage_id)
        if role is None:
            return jsonify(error="Not found"), 404
        if not can_write(role):
            return jsonify(error="Read-only access to this garage"), 403
        vehicle = VehicleRepository(db).create(garage_id, data, changed_by=current_user.id)
        # Re-attach a DVSA snapshot left behind by a deleted vehicle on the same plate.
        if (vehicle.get("registration") or "").strip():
            MotRepository(db).relink_detached(vehicle["id"], vehicle["registration"])
    analytics.capture(
        current_user.id,
        "vehicle.created",
        {"vehicle_id": vehicle["id"], "garage_id": garage_id, "kind": vehicle.get("kind")},
    )
    return jsonify(vehicle), 201


@bp.get("/api/vehicles/<int:vehicle_id>")
@login_required
def get_vehicle(vehicle_id: int) -> ResponseReturnValue:
    with get_db() as db:
        err = _check_vehicle(db, vehicle_id)
        if err:
            return err
        vehicle = VehicleRepository(db).get_detail(vehicle_id)
        assert vehicle is not None  # _check_vehicle verified existence
        vehicle["reminders"] = ServiceLogRepository(db).reminders(
            [vehicle["garage_id"]], vehicle_id=vehicle_id
        )
    return jsonify(vehicle)


@bp.put("/api/vehicles/<int:vehicle_id>")
@login_required
def update_vehicle(vehicle_id: int) -> ResponseReturnValue:
    data = _vehicle_data(request.json or {})
    if isinstance(data, tuple):
        return data
    with get_db() as db:
        err = _check_vehicle(db, vehicle_id, write=True)
        if err:
            return err
        old = VehicleRepository(db).get_by_id(vehicle_id)
        result = VehicleRepository(db).update(vehicle_id, data, changed_by=current_user.id)
        mot_repo = MotRepository(db)
        # Drop any attached DVSA/MOT and tax data when the registration change means it no
        # longer applies (the form prompts the user before sending this flag).
        if (request.json or {}).get("disconnect_mot"):
            mot_repo.clear_for_vehicle(vehicle_id)
            TaxRepository(db).clear_for_vehicle(vehicle_id)
        # If the plate changed and nothing is attached, re-link a detached DVSA snapshot
        # left behind by a deleted vehicle on the new plate.
        new_reg = (result.get("registration") or "") if result else ""
        old_reg = (old or {}).get("registration") or ""
        if (
            new_reg.strip()
            and mot.normalise_registration(new_reg) != mot.normalise_registration(old_reg)
            and mot_repo.get_for_vehicle(vehicle_id) is None
        ):
            mot_repo.relink_detached(vehicle_id, new_reg)
        return jsonify(result)


@bp.delete("/api/vehicles/<int:vehicle_id>")
@login_required
def delete_vehicle(vehicle_id: int) -> ResponseReturnValue:
    with get_db() as db:
        err = _check_vehicle(db, vehicle_id, write=True)
        if err:
            return err
        VehicleRepository(db).delete(vehicle_id)
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
        err = _check_vehicle(db, vehicle_id, write=True)
        if err:
            return err
        return jsonify(VehicleRepository(db).replace_specs(vehicle_id, specs))


@bp.get("/api/vehicles/<int:vehicle_id>/mileage")
@login_required
def mileage_series(vehicle_id: int) -> ResponseReturnValue:
    with get_db() as db:
        err = _check_vehicle(db, vehicle_id)
        if err:
            return err
        return jsonify(VehicleRepository(db).mileage_series(vehicle_id))


@bp.get("/api/vehicles/<int:vehicle_id>/history")
@login_required
def vehicle_history(vehicle_id: int) -> ResponseReturnValue:
    with get_db() as db:
        err = _check_vehicle(db, vehicle_id)
        if err:
            return err
        return jsonify(VehicleRepository(db).get_history(vehicle_id))


@bp.post("/api/vehicles/<int:vehicle_id>/revert/<int:version_id>")
@login_required
def revert_vehicle(vehicle_id: int, version_id: int) -> ResponseReturnValue:
    with get_db() as db:
        err = _check_vehicle(db, vehicle_id, write=True)
        if err:
            return err
        vehicle = VehicleRepository(db).revert(vehicle_id, version_id, changed_by=current_user.id)
    if not vehicle:
        return jsonify(error="Version not found"), 404
    return jsonify(vehicle)


@bp.get("/api/reminders")
@login_required
def all_reminders() -> ResponseReturnValue:
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
        return jsonify(ServiceLogRepository(db).reminders(garage_ids))
