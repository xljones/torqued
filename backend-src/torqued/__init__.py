import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory
from flask.typing import ResponseReturnValue
from flask_cors import CORS
from flask_login import LoginManager, current_user, logout_user

from torqued.domain.user import User

_DIST_DIR = str(Path(__file__).parent.parent.parent / "dist")

login_manager = LoginManager()


def create_app() -> Flask:
    from torqued.db import get_db, run_migrations
    from torqued.repositories.user_repository import UserRepository
    from torqued.routes import (
        admin,
        auth,
        export,
        odometer,
        photos,
        search,
        services,
        users,
        vehicles,
    )

    run_migrations()

    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        if os.environ.get("FLASK_DEBUG", "1") == "0":
            raise RuntimeError("SECRET_KEY environment variable must be set in production")
        secret_key = "dev-secret-key-change-in-production"

    app = Flask(__name__, static_folder=_DIST_DIR)
    app.config["SECRET_KEY"] = secret_key
    app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # photo uploads
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    CORS(app, supports_credentials=True)

    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str) -> User | None:
        with get_db() as db:
            row = UserRepository(db).get_by_id(int(user_id))
        if row:
            return User(
                id=row["id"],
                username=row["username"],
                created_at=row.get("created_at"),
                is_readonly=bool(row.get("is_readonly")),
                is_admin=bool(row.get("is_admin")),
                expires_at=row.get("expires_at"),
            )
        return None

    @login_manager.unauthorized_handler
    def unauthorized() -> tuple[Response, int]:
        return jsonify(error="Authentication required"), 401

    @app.before_request
    def enforce_auth() -> ResponseReturnValue | None:
        if not current_user.is_authenticated:
            return None
        if current_user.expires_at:
            try:
                if datetime.now(timezone.utc) >= datetime.fromisoformat(current_user.expires_at):
                    logout_user()
                    return jsonify(error="Account expired"), 401
            except ValueError:
                pass
        if (
            current_user.is_readonly
            and request.method not in ("GET", "HEAD", "OPTIONS")
            and request.path not in ("/api/auth/password", "/api/auth/logout")
        ):
            return jsonify(error="Read-only access"), 403
        return None

    for bp in (
        admin.bp,
        auth.bp,
        vehicles.bp,
        services.bp,
        odometer.bp,
        photos.bp,
        export.bp,
        search.bp,
        users.bp,
    ):
        app.register_blueprint(bp)

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def serve_frontend(path: str) -> Response:
        full = os.path.join(_DIST_DIR, path)
        if path and os.path.exists(full):
            return send_from_directory(_DIST_DIR, path)
        return send_from_directory(_DIST_DIR, "index.html")

    return app
