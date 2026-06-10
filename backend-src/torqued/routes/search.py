from flask import Blueprint, Response, jsonify, request
from flask_login import login_required

from torqued.db import get_db
from torqued.repositories.service_log_repository import ServiceLogRepository
from torqued.repositories.vehicle_repository import VehicleRepository

bp = Blueprint("search", __name__)


@bp.get("/api/search")
@login_required
def search() -> Response:
    q = request.args.get("q", "")
    with get_db() as db:
        results = VehicleRepository(db).search(q) + [
            {**s, "type": "service"} for s in ServiceLogRepository(db).search(q)
        ]
    return jsonify(results)
