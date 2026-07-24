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


def test_deployment_info_requires_auth(client: FlaskClient) -> None:
    assert client.get("/api/admin/deployment").status_code == 401


def test_deployment_info_requires_admin(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/admin/deployment").status_code == 403


def test_deployment_info_not_configured(admin_client: FlaskClient, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("BUILD_INFO_FILE", str(tmp_path / "missing.json"))
    r = admin_client.get("/api/admin/deployment")
    assert r.status_code == 200
    assert r.json["configured"] is False


def test_deployment_info_success(admin_client: FlaskClient, monkeypatch, tmp_path) -> None:
    build_info = tmp_path / "build-info.json"
    build_info.write_text(
        json.dumps(
            {
                "version": "0.0.1",
                "sha": "abc1234",
                "msg": "fix(admin): add deployment card",
                "built_at": "2026-06-23T20:00:00Z",
            }
        )
    )
    monkeypatch.setenv("BUILD_INFO_FILE", str(build_info))
    r = admin_client.get("/api/admin/deployment")
    assert r.status_code == 200
    assert r.json["configured"] is True
    assert r.json["version"] == "0.0.1"
    assert r.json["sha"] == "abc1234"
    assert r.json["msg"] == "fix(admin): add deployment card"
    assert r.json["built_at"] == "2026-06-23T20:00:00Z"
