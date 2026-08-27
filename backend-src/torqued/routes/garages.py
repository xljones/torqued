from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from torqued.access import garage_role
from torqued.db import IntegrityError, get_db
from torqued.repositories.garage_repository import ROLES, GarageRepository
from torqued.repositories.user_repository import UserRepository
from torqued.units import parse_distance, to_km

bp = Blueprint("garages", __name__)

# Generous sanity bounds — wide enough that nobody legitimate hits them, tight enough to
# reject a fat-fingered 900000. Enforced here rather than by a DB CHECK, as elsewhere.
MAX_WINDOW_DAYS = 3650
MAX_WINDOW_KM = to_km(100_000.0, "mi")


@bp.get("/api/garages")
@login_required
def list_garages() -> Response:
    with get_db() as db:
        repo = GarageRepository(db)
        if current_user.is_admin:
            garages = repo.list_all()
            for g in garages:
                g["role"] = "owner"
        else:
            garages = repo.list_for_user(current_user.id)
    return jsonify(garages)


@bp.post("/api/garages")
@login_required
def create_garage() -> ResponseReturnValue:
    if not current_user.is_admin:
        return jsonify(error="Admin access required"), 403
    d = request.json or {}
    name = (d.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400
    try:
        with get_db() as db:
            garage = GarageRepository(db).create(name)
        return jsonify(garage), 201
    except IntegrityError:
        return jsonify(error="Garage name already exists"), 409


@bp.put("/api/garages/<int:garage_id>")
@login_required
def rename_garage(garage_id: int) -> ResponseReturnValue:
    d = request.json or {}
    name = (d.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400
    try:
        with get_db() as db:
            repo = GarageRepository(db)
            if not repo.get_by_id(garage_id):
                return jsonify(error="Not found"), 404
            if garage_role(db, current_user, garage_id) != "owner":
                return jsonify(error="Garage owner access required"), 403
            return jsonify(repo.rename(garage_id, name))
    except IntegrityError:
        return jsonify(error="Garage name already exists"), 409


@bp.put("/api/garages/<int:garage_id>/settings")
@login_required
def update_garage_settings(garage_id: int) -> ResponseReturnValue:
    """Set a garage's maintenance reminder windows (owner only).

    Every threshold is optional; an omitted, empty or null value clears the column, which
    means "fall back to the application default" (torqued.reminders) — so the form gets a
    free "blank it to reset" affordance. The service distance arrives in the unit the user
    typed and is stored canonically in km alongside it, like a schedule interval.
    """
    d = request.json or {}

    def days(key: str) -> int | None:
        raw = d.get(key)
        if raw is None or raw == "":
            return None
        value = int(raw)  # a non-numeric value raises, caught below
        if not 1 <= value <= MAX_WINDOW_DAYS:
            raise ValueError(f"{key} must be between 1 and {MAX_WINDOW_DAYS} days")
        return value

    try:
        service_km, service_unit = parse_distance(
            d, value_key="reminder_service_distance", unit_key="reminder_service_unit"
        )
        if service_km is not None and not 0 < service_km <= MAX_WINDOW_KM:
            return jsonify(error="reminder_service_distance is out of range"), 400
        values = {
            "reminder_service_days": days("reminder_service_days"),
            "reminder_service_km": service_km,
            "reminder_service_unit": service_unit,
            "reminder_mot_days": days("reminder_mot_days"),
            "reminder_tax_days": days("reminder_tax_days"),
        }
    except (TypeError, ValueError) as err:
        return jsonify(error=str(err) or "reminder windows must be numeric"), 400

    with get_db() as db:
        repo = GarageRepository(db)
        if not repo.get_by_id(garage_id):
            return jsonify(error="Not found"), 404
        if garage_role(db, current_user, garage_id) != "owner":
            return jsonify(error="Garage owner access required"), 403
        return jsonify(repo.set_reminder_windows(garage_id, values))


@bp.delete("/api/garages/<int:garage_id>")
@login_required
def delete_garage(garage_id: int) -> ResponseReturnValue:
    if not current_user.is_admin:
        return jsonify(error="Admin access required"), 403
    with get_db() as db:
        if not GarageRepository(db).delete(garage_id):
            return jsonify(error="Not found"), 404
    return "", 204


# ── members ───────────────────────────────────────────────────────────────────


@bp.get("/api/garages/<int:garage_id>/members")
@login_required
def list_members(garage_id: int) -> ResponseReturnValue:
    with get_db() as db:
        repo = GarageRepository(db)
        if not repo.get_by_id(garage_id):
            return jsonify(error="Not found"), 404
        if garage_role(db, current_user, garage_id) is None:
            return jsonify(error="Not a member of this garage"), 403
        return jsonify(repo.list_members(garage_id))


@bp.post("/api/garages/<int:garage_id>/members")
@login_required
def add_member(garage_id: int) -> ResponseReturnValue:
    d = request.json or {}
    username = (d.get("username") or "").strip()
    role = d.get("role") or "member"
    if not username:
        return jsonify(error="username is required"), 400
    if role not in ROLES:
        return jsonify(error=f"role must be one of {', '.join(ROLES)}"), 400
    try:
        with get_db() as db:
            repo = GarageRepository(db)
            if not repo.get_by_id(garage_id):
                return jsonify(error="Not found"), 404
            if garage_role(db, current_user, garage_id) != "owner":
                return jsonify(error="Garage owner access required"), 403
            user = UserRepository(db).get_by_username(username)
            if not user:
                return jsonify(error="No user with that username"), 404
            member = repo.add_member(garage_id, user["id"], role)
        return jsonify(member), 201
    except IntegrityError:
        return jsonify(error="Already a member of this garage"), 409


@bp.put("/api/garages/<int:garage_id>/members/<int:user_id>")
@login_required
def set_member_role(garage_id: int, user_id: int) -> ResponseReturnValue:
    d = request.json or {}
    role = d.get("role")
    if role not in ROLES:
        return jsonify(error=f"role must be one of {', '.join(ROLES)}"), 400
    with get_db() as db:
        repo = GarageRepository(db)
        if garage_role(db, current_user, garage_id) != "owner":
            return jsonify(error="Garage owner access required"), 403
        if not repo.set_member_role(garage_id, user_id, role):
            return jsonify(error="Not found"), 404
        return jsonify(repo.list_members(garage_id))


@bp.delete("/api/garages/<int:garage_id>/members/<int:user_id>")
@login_required
def remove_member(garage_id: int, user_id: int) -> ResponseReturnValue:
    with get_db() as db:
        repo = GarageRepository(db)
        if garage_role(db, current_user, garage_id) != "owner":
            return jsonify(error="Garage owner access required"), 403
        if not repo.remove_member(garage_id, user_id):
            return jsonify(error="Not found"), 404
    return "", 204
