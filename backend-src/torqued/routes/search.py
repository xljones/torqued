from flask import Blueprint, Response, jsonify, request
from flask_login import current_user, login_required

from torqued.access import accessible_garage_ids
from torqued.db import get_db
from torqued.repositories.service_log_repository import ServiceLogRepository
from torqued.repositories.vehicle_repository import VehicleRepository

bp = Blueprint("search", __name__)


@bp.get("/api/search")
@login_required
def search() -> Response:
    q = request.args.get("q", "")
    with get_db() as db:
        garage_ids = accessible_garage_ids(db, current_user)
        results = VehicleRepository(db).search(q, garage_ids) + [
            {**s, "type": "service"} for s in ServiceLogRepository(db).search(q, garage_ids)
        ]
    return jsonify(results)
