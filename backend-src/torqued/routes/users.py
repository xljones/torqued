import sqlite3
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from torqued.db import get_db
from torqued.repositories.garage_repository import ROLES, GarageRepository
from torqued.repositories.user_repository import UserRepository

bp = Blueprint("users", __name__)


@bp.get("/api/users")
@login_required
def list_users() -> ResponseReturnValue:
    if not current_user.is_admin:
        return jsonify(error="Admin access required"), 403
    with get_db() as db:
        return jsonify(UserRepository(db).list_all()), 200


@bp.post("/api/users")
@login_required
def create_user() -> ResponseReturnValue:
    if not current_user.is_admin:
        return jsonify(error="Admin access required"), 403
    d = request.json or {}
    username = (d.get("username") or "").strip()
    password = d.get("password") or ""
    ttl_days = d.get("ttl_days")
    is_admin = bool(d.get("is_admin"))
    garage_id = d.get("garage_id")
    role = d.get("role") or "member"
    if not username or not password:
        return jsonify(error="username and password are required"), 400
    if role not in ROLES:
        return jsonify(error=f"role must be one of {', '.join(ROLES)}"), 400
    expires_at = None
    if ttl_days is not None:
        try:
            ttl_days = int(ttl_days)
            if ttl_days < 1:
                raise ValueError
        except (ValueError, TypeError):
            return jsonify(error="ttl_days must be a positive integer"), 400
        expires_at = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat()
    try:
        with get_db() as db:
            if garage_id is not None and not GarageRepository(db).get_by_id(int(garage_id)):
                return jsonify(error="Garage not found"), 400
            user = UserRepository(db).create(
                username, password, is_admin=is_admin, expires_at=expires_at
            )
            if garage_id is not None:
                GarageRepository(db).add_member(int(garage_id), user["id"], role)
            user["memberships"] = UserRepository(db).memberships(user["id"])
        return jsonify(user), 201
    except sqlite3.IntegrityError:
        return jsonify(error="Username already exists"), 409


@bp.put("/api/users/<int:user_id>/password")
@login_required
def reset_password(user_id: int) -> ResponseReturnValue:
    if not current_user.is_admin:
        return jsonify(error="Admin access required"), 403
    d = request.json or {}
    password = d.get("password") or ""
    if len(password) < 6:
        return jsonify(error="Password must be at least 6 characters"), 400
    with get_db() as db:
        repo = UserRepository(db)
        target = repo.get_by_id(user_id)
        if not target:
            return jsonify(error="Not found"), 404
        if target["is_admin"] and user_id != current_user.id:
            return jsonify(error="Admin passwords can only be changed by the account holder"), 403
        repo.set_password(user_id, password)
    return "", 204


@bp.delete("/api/users/<int:user_id>")
@login_required
def delete_user(user_id: int) -> ResponseReturnValue:
    if not current_user.is_admin:
        return jsonify(error="Admin access required"), 403
    if user_id == current_user.id:
        return jsonify(error="Cannot delete your own account"), 400
    with get_db() as db:
        repo = UserRepository(db)
        target = repo.get_by_id(user_id)
        if not target:
            return jsonify(error="Not found"), 404
        if target["is_admin"]:
            return jsonify(error="Admin accounts cannot be deleted via the API"), 403
        repo.delete(user_id)
    return "", 204
