from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from torqued.access import garage_role
from torqued.db import IntegrityError, get_db
from torqued.repositories.garage_repository import ROLES, GarageRepository
from torqued.repositories.user_repository import UserRepository

bp = Blueprint("garages", __name__)


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
