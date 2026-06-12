from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue
from flask_login import login_required

from torqued import dtc

bp = Blueprint("codes", __name__)


@bp.get("/api/codes/<raw_code>")
@login_required
def lookup_code(raw_code: str) -> ResponseReturnValue:
    result = dtc.lookup(raw_code)
    if result is None:
        return jsonify(error="Not a valid DTC — expected e.g. P0016, C0035, U0100"), 400
    return jsonify(result)


@bp.get("/api/codes")
@login_required
def search_codes() -> Response:
    q = request.args.get("q", "")
    if not q.strip():
        return jsonify(dtc.list_all())
    return jsonify(dtc.search(q))
