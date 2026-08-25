from typing import Any

from flask import Blueprint, Response, jsonify, request, session
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required, login_user, logout_user

from torqued import analytics
from torqued.db import get_db
from torqued.domain.user import User
from torqued.repositories.user_repository import UserRepository

bp = Blueprint("auth", __name__)


def _user_dict(row: dict[str, Any], memberships: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "is_admin": bool(row.get("is_admin")),
        "expires_at": row.get("expires_at"),
        "memberships": memberships,
    }


def _user_obj(row: dict[str, Any]) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        is_admin=bool(row.get("is_admin")),
        expires_at=row.get("expires_at"),
    )


@bp.post("/api/auth/login")
def login() -> ResponseReturnValue:
    d = request.json or {}
    username = (d.get("username") or "").strip()
    password = d.get("password") or ""
    if not username or not password:
        return jsonify(error="Username and password required"), 400
    with get_db() as db:
        repo = UserRepository(db)
        row = repo.verify_password(username, password)
        memberships = repo.memberships(row["id"]) if row else []
    if not row:
        return jsonify(error="Invalid username or password"), 401
    user = _user_obj(row)
    if not user.is_active:
        return jsonify(error="Account expired"), 401
    session.permanent = True
    login_user(user)
    analytics.capture(
        user.id,
        "user.logged_in",
        {"is_admin": user.is_admin},
    )
    return jsonify(_user_dict(row, memberships))


@bp.post("/api/auth/logout")
def logout() -> ResponseReturnValue:
    logout_user()
    return "", 204


@bp.get("/api/auth/me")
@login_required
def me() -> Response:
    with get_db() as db:
        memberships = UserRepository(db).memberships(current_user.id)
    return jsonify(
        id=current_user.id,
        username=current_user.username,
        is_admin=bool(current_user.is_admin),
        expires_at=current_user.expires_at,
        memberships=memberships,
    )


@bp.put("/api/auth/password")
@login_required
def change_password() -> ResponseReturnValue:
    d = request.json or {}
    current_pw = d.get("current_password") or ""
    new_pw = d.get("new_password") or ""
    if not current_pw or not new_pw:
        return jsonify(error="current_password and new_password required"), 400
    if len(new_pw) < 6:
        return jsonify(error="New password must be at least 6 characters"), 400
    with get_db() as db:
        ok = UserRepository(db).change_password(current_user.id, current_pw, new_pw)
    if not ok:
        return jsonify(error="Current password is incorrect"), 403
    return "", 204
