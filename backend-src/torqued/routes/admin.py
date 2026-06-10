import json
import os
import urllib.error
import urllib.request

from flask import Blueprint, jsonify
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

bp = Blueprint("admin", __name__)

_PA_BASE = "https://www.pythonanywhere.com"


def _pa_get(username: str, token: str, path: str) -> dict | list:
    url = f"{_PA_BASE}/api/v0/user/{username}{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"Token {token}"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode())


@bp.get("/api/admin/pythonanywhere")
@login_required
def pythonanywhere_stats() -> ResponseReturnValue:
    if not current_user.is_admin:
        return jsonify(error="Admin access required"), 403

    token = os.environ.get("PA_API_TOKEN", "").strip()
    username = os.environ.get("PA_USERNAME", "").strip()
    if not token or not username:
        return jsonify(configured=False), 200

    try:
        cpu = _pa_get(username, token, "/cpu/")
        webapps = _pa_get(username, token, "/webapps/")
        schedule = _pa_get(username, token, "/schedule/")
    except urllib.error.HTTPError as e:
        return jsonify(configured=True, error=f"PythonAnywhere API error: {e.code} {e.reason}"), 502
    except Exception as e:
        return jsonify(configured=True, error=f"Could not reach PythonAnywhere API: {e}"), 502

    return jsonify(
        configured=True,
        cpu=cpu,
        webapps=webapps,
        schedule=schedule,
    ), 200
