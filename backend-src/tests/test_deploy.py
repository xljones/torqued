"""Tests for the self-redeploy webhook (routes/deploy.py).

The deploy subprocess is always mocked, so no real git/pip/migrate/reload ever runs. A
helper signs requests exactly as the CI shell does (HMAC-SHA256 over
``f"{ts}.".encode() + body``), proving the server accepts what CI produces.
"""
import hmac
import time
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from flask.testing import FlaskClient

from torqued.routes import deploy

_SECRET = "super-secret-deploy-key"
_URL = "/api/deploy/webhook"
_BODY = b'{"ref":"deploy"}'


def _sign(secret: str, ts: str, body: bytes = _BODY) -> str:
    return hmac.new(secret.encode(), f"{ts}.".encode() + body, sha256).hexdigest()


def _now() -> str:
    return str(int(time.time()))


@pytest.fixture
def recorded_popen(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace subprocess.Popen in the deploy module; record the call instead of running."""
    calls: dict[str, Any] = {"count": 0}

    def fake_popen(args: list[str], **kwargs: Any) -> object:
        calls["count"] += 1
        calls["args"] = args
        calls["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(deploy.subprocess, "Popen", fake_popen)
    return calls


@pytest.fixture
def enabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Opt the webhook in with a real secret and a temp log file. Returns the log path."""
    monkeypatch.setenv("ENABLE_DEPLOY_WEBHOOK", "1")
    monkeypatch.setenv("DEPLOY_WEBHOOK_SECRET", _SECRET)
    log = tmp_path / "deploy.log"
    monkeypatch.setenv("DEPLOY_LOG_FILE", str(log))
    return log


def _post(client: FlaskClient, ts: str, sig: str, body: bytes = _BODY) -> Any:
    return client.post(
        _URL,
        data=body,
        headers={"X-Deploy-Timestamp": ts, "X-Deploy-Signature": sig},
        content_type="application/json",
    )


def test_valid_signature_triggers_detached_deploy(
    client: FlaskClient, enabled: Path, recorded_popen: dict[str, Any]
) -> None:
    ts = _now()
    r = _post(client, ts, _sign(_SECRET, ts))
    assert r.status_code == 202
    assert r.json["status"] == "accepted"
    assert recorded_popen["count"] == 1
    assert recorded_popen["args"] == ["bash", str(deploy._SCRIPT_PATH)]
    assert recorded_popen["kwargs"]["start_new_session"] is True
    # The attempt is logged; the secret is never written to the log.
    contents = enabled.read_text()
    assert "accepted" in contents
    assert _SECRET not in contents


def test_invalid_signature_rejected(
    client: FlaskClient, enabled: Path, recorded_popen: dict[str, Any]
) -> None:
    r = _post(client, _now(), "deadbeef")
    assert r.status_code == 401
    assert recorded_popen["count"] == 0
    assert "bad-signature" in enabled.read_text()


def test_signature_over_wrong_body_rejected(
    client: FlaskClient, enabled: Path, recorded_popen: dict[str, Any]
) -> None:
    ts = _now()
    sig = _sign(_SECRET, ts, b'{"ref":"something-else"}')  # signs a different body
    r = _post(client, ts, sig)  # but sends _BODY
    assert r.status_code == 401
    assert recorded_popen["count"] == 0


def test_missing_signature_header_rejected(
    client: FlaskClient, enabled: Path, recorded_popen: dict[str, Any]
) -> None:
    r = client.post(_URL, data=_BODY, headers={"X-Deploy-Timestamp": _now()})
    assert r.status_code == 401
    assert recorded_popen["count"] == 0


def test_missing_timestamp_header_rejected(
    client: FlaskClient, enabled: Path, recorded_popen: dict[str, Any]
) -> None:
    r = client.post(_URL, data=_BODY, headers={"X-Deploy-Signature": "x"})
    assert r.status_code == 401
    assert recorded_popen["count"] == 0
    assert "stale-timestamp" in enabled.read_text()


def test_garbage_timestamp_rejected(
    client: FlaskClient, enabled: Path, recorded_popen: dict[str, Any]
) -> None:
    r = _post(client, "not-a-number", "x")
    assert r.status_code == 401
    assert recorded_popen["count"] == 0


def test_stale_timestamp_rejected(
    client: FlaskClient, enabled: Path, recorded_popen: dict[str, Any]
) -> None:
    ts = str(int(time.time()) - 3600)  # an hour old
    r = _post(client, ts, _sign(_SECRET, ts))
    assert r.status_code == 401
    assert recorded_popen["count"] == 0


def test_future_timestamp_rejected(
    client: FlaskClient, enabled: Path, recorded_popen: dict[str, Any]
) -> None:
    ts = str(int(time.time()) + 3600)
    r = _post(client, ts, _sign(_SECRET, ts))
    assert r.status_code == 401
    assert recorded_popen["count"] == 0


def test_disabled_without_opt_in_returns_404(
    client: FlaskClient, recorded_popen: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Secret present but the flag is off → inert, hidden as a 404.
    monkeypatch.setenv("DEPLOY_WEBHOOK_SECRET", _SECRET)
    monkeypatch.delenv("ENABLE_DEPLOY_WEBHOOK", raising=False)
    ts = _now()
    r = _post(client, ts, _sign(_SECRET, ts))
    assert r.status_code == 404
    assert recorded_popen["count"] == 0


def test_missing_secret_returns_404(
    client: FlaskClient, recorded_popen: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENABLE_DEPLOY_WEBHOOK", "1")
    monkeypatch.delenv("DEPLOY_WEBHOOK_SECRET", raising=False)
    r = _post(client, _now(), "x")
    assert r.status_code == 404
    assert recorded_popen["count"] == 0


def test_dev_fallback_secret_refused(
    client: FlaskClient, recorded_popen: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENABLE_DEPLOY_WEBHOOK", "1")
    monkeypatch.setenv("DEPLOY_WEBHOOK_SECRET", "dev-secret-key-change-in-production")
    r = _post(client, _now(), "x")
    assert r.status_code == 404
    assert recorded_popen["count"] == 0
