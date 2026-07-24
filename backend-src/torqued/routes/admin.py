import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from flask import Blueprint, jsonify
from flask.typing import ResponseReturnValue

from torqued.access import admin_required

bp = Blueprint("admin", __name__)

_PA_BASE = "https://www.pythonanywhere.com"


def _build_info_path() -> str:
    # Written into dist/ by CI on each deploy (see .github/workflows/ci.yml). The default
    # resolves to <repo root>/dist/build-info.json on PythonAnywhere; BUILD_INFO_FILE
    # overrides it (used by tests).
    return os.environ.get(
        "BUILD_INFO_FILE",
        str(Path(__file__).parent.parent.parent.parent / "dist" / "build-info.json"),
    )


@bp.get("/api/admin/deployment")
@admin_required
def deployment_info() -> ResponseReturnValue:
    try:
        with open(_build_info_path(), encoding="utf-8") as fh:
            info = json.load(fh)
    except (OSError, ValueError):
        # No dist/build-info.json yet (e.g. dev, or before the first deploy).
        return jsonify(configured=False), 200

    return jsonify(
        configured=True,
        version=info.get("version"),
        sha=info.get("sha"),
        msg=info.get("msg"),
        built_at=info.get("built_at"),
    ), 200


def _pa_get(username: str, token: str, path: str) -> dict | list:
    url = f"{_PA_BASE}/api/v0/user/{username}{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"Token {token}"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode())


@bp.get("/api/admin/pythonanywhere")
@admin_required
def pythonanywhere_stats() -> ResponseReturnValue:
    token = os.environ.get("PA_API_TOKEN", "").strip()
    username = os.environ.get("PA_USERNAME", "").strip()
    if not token or not username:
        return jsonify(configured=False), 200

    try:
        cpu = _pa_get(username, token, "/cpu/")
        webapps = _pa_get(username, token, "/webapps/")
        schedule = _pa_get(username, token, "/schedule/")
    except urllib.error.HTTPError as e:
        error = f"PythonAnywhere API error: {e.code} {e.reason}"
        e.close()
        return jsonify(configured=True, error=error), 502
    except Exception as e:
        return jsonify(configured=True, error=f"Could not reach PythonAnywhere API: {e}"), 502

    return jsonify(
        configured=True,
        cpu=cpu,
        webapps=webapps,
        schedule=schedule,
    ), 200
