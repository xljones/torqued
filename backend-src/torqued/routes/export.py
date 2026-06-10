import csv
import io
import json
from datetime import date
from typing import Any

from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue
from flask_login import login_required

from torqued.db import get_db
from torqued.repositories.service_log_repository import ServiceLogRepository

bp = Blueprint("export", __name__)


def _csv_response(rows: list[dict[str, Any]], delimiter: str, filename: str) -> Response:
    out = io.StringIO()
    if rows:
        writer = csv.DictWriter(out, fieldnames=list(rows[0].keys()), delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)
    mimetype = "text/tab-separated-values" if delimiter == "\t" else "text/csv"
    return Response(
        out.getvalue(),
        mimetype=mimetype,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@bp.get("/api/export/services")
@login_required
def export_services() -> ResponseReturnValue:
    fmt = request.args.get("format", "csv")
    vehicle_id_raw = request.args.get("vehicle_id")
    vehicle_id = None
    if vehicle_id_raw:
        try:
            vehicle_id = int(vehicle_id_raw)
        except ValueError:
            return jsonify(error="vehicle_id must be an integer"), 400

    with get_db() as db:
        rows = ServiceLogRepository(db).export_flat(vehicle_id=vehicle_id)

    stem = f"torqued-services-{date.today().isoformat()}"
    if fmt == "json":
        return Response(
            json.dumps(rows, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename={stem}.json"},
        )
    if fmt == "tsv":
        return _csv_response(rows, "\t", f"{stem}.tsv")
    if fmt == "csv":
        return _csv_response(rows, ",", f"{stem}.csv")
    return jsonify(error=f"unknown format: {fmt}"), 400
