import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, jsonify, send_from_directory
from flask.typing import ResponseReturnValue
from flask_cors import CORS
from flask_login import LoginManager, current_user, logout_user

from torqued.domain.user import User

_DIST_DIR = str(Path(__file__).parent.parent.parent / "dist")

login_manager = LoginManager()


# A deploy can briefly take the app offline (e.g. while migrations run). When this
# flag file exists every request gets a short maintenance page instead. `make
# deploy-pa` creates it around the migration step and removes it afterwards.
_MAINTENANCE_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Torqued — maintenance</title>
<style>
  body { font-family: system-ui, -apple-system, sans-serif; background: #f5f4f0;
         color: #1a1714; display: grid; place-items: center; min-height: 100vh; margin: 0; }
  .box { text-align: center; max-width: 28rem; padding: 2rem; }
  h1 { margin: 0 0 .5rem; }
  p { color: #6b6560; }
</style></head>
<body><div class="box">
  <h1>🔧 Down for maintenance</h1>
  <p>Torqued is being updated — this usually takes under a minute. Please refresh shortly.</p>
</div></body></html>"""


def _maintenance_flag() -> str:
    return os.environ.get(
        "MAINTENANCE_FILE", str(Path(__file__).parent.parent.parent / "MAINTENANCE")
    )


def create_app() -> Flask:
    from torqued.db import get_db, run_migrations
    from torqued.repositories.user_repository import UserRepository
    from torqued.routes import (
        admin,
        auth,
        codes,
        deploy,
        export,
        garages,
        mot,
        odometer,
        photos,
        schedules,
        search,
        services,
        tax,
        users,
        vehicles,
    )

    # On PythonAnywhere, migrations are applied explicitly (single process) by
    # `make migrate` / `make deploy-pa`, behind a maintenance page. Skip the
    # per-worker startup migration there: PA boots several web workers at once and on
    # a fresh database they would race to apply the schema, leaving it half-built
    # (e.g. "table users already exists"). Locally and in Docker the startup migration
    # stays, so the app is ready on first boot with no extra step.
    if not os.environ.get("PYTHONANYWHERE_SITE"):
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
                is_admin=bool(row.get("is_admin")),
                expires_at=row.get("expires_at"),
            )
        return None

    @login_manager.unauthorized_handler
    def unauthorized() -> tuple[Response, int]:
        return jsonify(error="Authentication required"), 401

    @app.before_request
    def maintenance_gate() -> ResponseReturnValue | None:
        if os.path.exists(_maintenance_flag()):
            return Response(
                _MAINTENANCE_HTML, status=503, mimetype="text/html",
                headers={"Retry-After": "30"},
            )
        return None

    @app.before_request
    def enforce_auth() -> ResponseReturnValue | None:
        # Read-only enforcement is per-garage and handled in the routes via
        # torqued.access; this hook only enforces account expiry.
        if not current_user.is_authenticated:
            return None
        if current_user.expires_at:
            try:
                if datetime.now(timezone.utc) >= datetime.fromisoformat(current_user.expires_at):
                    logout_user()
                    return jsonify(error="Account expired"), 401
            except ValueError:
                pass
        return None

    for bp in (
        admin.bp,
        auth.bp,
        garages.bp,
        vehicles.bp,
        services.bp,
        odometer.bp,
        mot.bp,
        tax.bp,
        photos.bp,
        schedules.bp,
        codes.bp,
        deploy.bp,
        export.bp,
        search.bp,
        users.bp,
    ):
        app.register_blueprint(bp)

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def serve_frontend(path: str) -> ResponseReturnValue:
        # Never fall through to the SPA for an unmatched API route: that would return
        # index.html with a 200, which clients can't parse as JSON. Return a real 404.
        if path.startswith("api/"):
            return jsonify(error="Not found"), 404
        full = os.path.join(_DIST_DIR, path)
        if path and os.path.exists(full):
            return send_from_directory(_DIST_DIR, path)
        return send_from_directory(_DIST_DIR, "index.html")

    return app
