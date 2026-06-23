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
_NEON_BASE = "https://console.neon.tech/api/v2"


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


def _neon_get(api_key: str, path: str) -> dict:
    url = f"{_NEON_BASE}{path}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode())


def _compute_limit_seconds(project: dict) -> int | None:
    # Neon exposes no plan-inherent compute allowance, so the denominator for the
    # compute % comes from an explicit NEON_COMPUTE_LIMIT_HOURS (the plan's monthly
    # compute-hours, e.g. 100 on Free), else a configured consumption quota, else none.
    override = os.environ.get("NEON_COMPUTE_LIMIT_HOURS", "").strip()
    if override:
        try:
            return int(float(override) * 3600) or None
        except ValueError:
            pass
    quota = project.get("settings", {}).get("quota", {}).get("compute_time_seconds", 0) or 0
    return int(quota) or None


@bp.get("/api/admin/neon")
@admin_required
def neon_stats() -> ResponseReturnValue:
    api_key = os.environ.get("NEON_API_KEY", "").strip()
    if not api_key:
        return jsonify(configured=False), 200

    project_id = os.environ.get("NEON_PROJECT_ID", "").strip()
    try:
        if not project_id:
            projects = _neon_get(api_key, "/projects").get("projects", [])
            if not projects:
                return (
                    jsonify(configured=True, error="No Neon projects found for this API key"),
                    502,
                )
            project_id = projects[0]["id"]
        project = _neon_get(api_key, f"/projects/{project_id}").get("project", {})
    except urllib.error.HTTPError as e:
        error = f"Neon API error: {e.code} {e.reason}"
        e.close()
        return jsonify(configured=True, error=error), 502
    except Exception as e:
        return jsonify(configured=True, error=f"Could not reach Neon API: {e}"), 502

    storage = project.get("synthetic_storage_size", project.get("synthetic_storage_size_bytes", 0))
    active = project.get("active_time", project.get("active_time_seconds", 0))
    storage_limit = project.get("branch_logical_size_limit_bytes") or None
    return jsonify(
        configured=True,
        project={
            "id": project.get("id"),
            "name": project.get("name"),
            "region": project.get("region_id"),
            "pg_version": project.get("pg_version"),
        },
        storage_bytes=storage or 0,
        storage_limit_bytes=storage_limit,
        cpu_seconds=project.get("cpu_used_sec", 0) or 0,
        cpu_limit_seconds=_compute_limit_seconds(project),
        active_seconds=active or 0,
        quota_reset_at=project.get("quota_reset_at"),
        last_active_at=project.get("compute_last_active_at"),
    ), 200
