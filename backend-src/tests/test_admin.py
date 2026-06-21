import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

from flask.testing import FlaskClient


def test_pythonanywhere_stats_requires_auth(client: FlaskClient) -> None:
    assert client.get("/api/admin/pythonanywhere").status_code == 401


def test_pythonanywhere_stats_requires_admin(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/admin/pythonanywhere").status_code == 403


def test_pythonanywhere_stats_not_configured(admin_client: FlaskClient, monkeypatch) -> None:
    monkeypatch.delenv("PA_API_TOKEN", raising=False)
    monkeypatch.delenv("PA_USERNAME", raising=False)
    r = admin_client.get("/api/admin/pythonanywhere")
    assert r.status_code == 200
    assert r.json["configured"] is False


def _mock_urlopen(responses: list[dict]):
    responses_iter = iter(responses)

    def urlopen(req, timeout=None):
        data = json.dumps(next(responses_iter)).encode()
        cm = MagicMock()
        cm.__enter__ = lambda s: MagicMock(read=lambda: data)
        cm.__exit__ = MagicMock(return_value=False)
        return cm

    return urlopen


def test_pythonanywhere_stats_success(admin_client: FlaskClient, monkeypatch) -> None:
    monkeypatch.setenv("PA_API_TOKEN", "tok")
    monkeypatch.setenv("PA_USERNAME", "user")

    cpu = {"daily_cpu_limit_seconds": 100, "daily_cpu_total_usage_seconds": 42.0, "next_reset_time": "2026-06-02T00:00:00"}
    webapps = [{"id": 1, "domain_name": "user.pythonanywhere.com", "enabled": True, "python_version": "3.12"}]
    schedule = [{"id": 1, "enabled": True, "interval": "daily", "hour": 2, "minute": 0, "command": "python foo.py", "description": "Nightly job"}]

    with patch("torqued.routes.admin.urllib.request.urlopen", side_effect=_mock_urlopen([cpu, webapps, schedule])):
        r = admin_client.get("/api/admin/pythonanywhere")

    assert r.status_code == 200
    assert r.json["configured"] is True
    assert r.json["cpu"]["daily_cpu_limit_seconds"] == 100
    assert r.json["webapps"][0]["domain_name"] == "user.pythonanywhere.com"
    assert r.json["schedule"][0]["command"] == "python foo.py"


def test_pythonanywhere_stats_http_error(admin_client: FlaskClient, monkeypatch) -> None:
    monkeypatch.setenv("PA_API_TOKEN", "tok")
    monkeypatch.setenv("PA_USERNAME", "user")

    exc = urllib.error.HTTPError(url="", code=401, msg="Unauthorized", hdrs=None, fp=None)
    with patch("torqued.routes.admin.urllib.request.urlopen", side_effect=exc):
        r = admin_client.get("/api/admin/pythonanywhere")

    assert r.status_code == 502
    assert r.json["configured"] is True
    assert "401" in r.json["error"]


def test_pythonanywhere_stats_connection_error(admin_client: FlaskClient, monkeypatch) -> None:
    monkeypatch.setenv("PA_API_TOKEN", "tok")
    monkeypatch.setenv("PA_USERNAME", "user")

    with patch("torqued.routes.admin.urllib.request.urlopen", side_effect=OSError("timeout")):
        r = admin_client.get("/api/admin/pythonanywhere")

    assert r.status_code == 502
    assert r.json["configured"] is True
    assert "timeout" in r.json["error"]


def test_neon_stats_requires_auth(client: FlaskClient) -> None:
    assert client.get("/api/admin/neon").status_code == 401


def test_neon_stats_requires_admin(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/admin/neon").status_code == 403


def test_neon_stats_not_configured(admin_client: FlaskClient, monkeypatch) -> None:
    monkeypatch.delenv("NEON_API_KEY", raising=False)
    r = admin_client.get("/api/admin/neon")
    assert r.status_code == 200
    assert r.json["configured"] is False


def test_neon_stats_success(admin_client: FlaskClient, monkeypatch) -> None:
    monkeypatch.setenv("NEON_API_KEY", "key")
    monkeypatch.setenv("NEON_PROJECT_ID", "proj-123")

    project = {
        "project": {
            "id": "proj-123",
            "name": "torqued-db",
            "region_id": "aws-eu-west-2",
            "pg_version": 17,
            "synthetic_storage_size": 134217728,
            "branch_logical_size_limit_bytes": 536870912,
            "cpu_used_sec": 7200,
            "active_time": 3600,
            "quota_reset_at": "2026-07-01T00:00:00Z",
            "compute_last_active_at": "2026-06-21T09:00:00Z",
        }
    }

    with patch("torqued.routes.admin.urllib.request.urlopen", side_effect=_mock_urlopen([project])):
        r = admin_client.get("/api/admin/neon")

    assert r.status_code == 200
    assert r.json["configured"] is True
    assert r.json["project"]["name"] == "torqued-db"
    assert r.json["project"]["region"] == "aws-eu-west-2"
    assert r.json["storage_bytes"] == 134217728
    assert r.json["storage_limit_bytes"] == 536870912
    assert r.json["cpu_seconds"] == 7200
    assert r.json["active_seconds"] == 3600
    assert r.json["quota_reset_at"] == "2026-07-01T00:00:00Z"
    assert r.json["last_active_at"] == "2026-06-21T09:00:00Z"


def test_neon_stats_success_autodiscover(admin_client: FlaskClient, monkeypatch) -> None:
    monkeypatch.setenv("NEON_API_KEY", "key")
    monkeypatch.delenv("NEON_PROJECT_ID", raising=False)

    projects = {"projects": [{"id": "proj-abc", "name": "torqued-db"}]}
    # The *_bytes / *_seconds variant names exercise the defensive field fallbacks.
    project = {
        "project": {
            "id": "proj-abc",
            "name": "torqued-db",
            "region_id": "aws-eu-west-2",
            "pg_version": 17,
            "synthetic_storage_size_bytes": 268435456,
            "cpu_used_sec": 1800,
            "active_time_seconds": 900,
            "quota_reset_at": "2026-07-01T00:00:00Z",
            "compute_last_active_at": None,
        }
    }

    with patch(
        "torqued.routes.admin.urllib.request.urlopen",
        side_effect=_mock_urlopen([projects, project]),
    ):
        r = admin_client.get("/api/admin/neon")

    assert r.status_code == 200
    assert r.json["configured"] is True
    assert r.json["project"]["id"] == "proj-abc"
    assert r.json["storage_bytes"] == 268435456
    assert r.json["storage_limit_bytes"] is None
    assert r.json["active_seconds"] == 900
    assert r.json["last_active_at"] is None


def test_neon_stats_no_projects(admin_client: FlaskClient, monkeypatch) -> None:
    monkeypatch.setenv("NEON_API_KEY", "key")
    monkeypatch.delenv("NEON_PROJECT_ID", raising=False)

    with patch(
        "torqued.routes.admin.urllib.request.urlopen",
        side_effect=_mock_urlopen([{"projects": []}]),
    ):
        r = admin_client.get("/api/admin/neon")

    assert r.status_code == 502
    assert r.json["configured"] is True
    assert "No Neon projects" in r.json["error"]


def test_neon_stats_http_error(admin_client: FlaskClient, monkeypatch) -> None:
    monkeypatch.setenv("NEON_API_KEY", "key")
    monkeypatch.setenv("NEON_PROJECT_ID", "proj-123")

    exc = urllib.error.HTTPError(url="", code=401, msg="Unauthorized", hdrs=None, fp=None)
    with patch("torqued.routes.admin.urllib.request.urlopen", side_effect=exc):
        r = admin_client.get("/api/admin/neon")

    assert r.status_code == 502
    assert r.json["configured"] is True
    assert "401" in r.json["error"]


def test_neon_stats_connection_error(admin_client: FlaskClient, monkeypatch) -> None:
    monkeypatch.setenv("NEON_API_KEY", "key")
    monkeypatch.setenv("NEON_PROJECT_ID", "proj-123")

    with patch("torqued.routes.admin.urllib.request.urlopen", side_effect=OSError("timeout")):
        r = admin_client.get("/api/admin/neon")

    assert r.status_code == 502
    assert r.json["configured"] is True
    assert "timeout" in r.json["error"]
