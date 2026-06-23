"""Self-redeploy webhook.

Lets the GitHub Actions deploy job trigger a PythonAnywhere redeploy over HTTP,
authenticated by an HMAC-SHA256 signature so nobody else can fire a deploy.

Safety model (mirrors the dev DB switcher in torqued.db):
  * Inert unless explicitly opted in — both ENABLE_DEPLOY_WEBHOOK=1 *and* a real
    DEPLOY_WEBHOOK_SECRET must be set, else the route 404s and hides itself.
  * The secret is dedicated, never the Flask SECRET_KEY, so the CI store never holds
    cookie-signing material and the secret rotates without logging users out. The known
    dev fallback is refused, so an accidentally-enabled dev box can't be triggered.
  * The request is verified before any side effect: the signature covers the exact body
    bytes plus a timestamp that is itself inside the signed payload (so a captured body
    can't be replayed with a fresh timestamp), checked in constant time within a skew
    window.
  * The deploy runs in a fully detached child process, and the handler returns 202
    immediately. The deploy's last step reloads this very WSGI worker; decoupling means
    that reload can't kill the request, and pip/migrate can't blow the worker's request
    timeout. The steps live in scripts/deploy_pa.sh — the same script `make deploy-pa`
    runs — so the manual and automated paths can't diverge.
"""
import hmac
import os
import subprocess
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

bp = Blueprint("deploy", __name__)

# scripts/deploy_pa.sh, resolved relative to this file (like _DIST_DIR in __init__.py).
# routes/ -> torqued/ -> backend-src/ -> repo root.
_SCRIPT_PATH = Path(__file__).parent.parent.parent.parent / "scripts" / "deploy_pa.sh"

# Reject a signed request whose timestamp is more than this many seconds from now, in
# either direction — bounds the replay window.
_MAX_SKEW_SECONDS = 300

# Refusing this value keeps the webhook inert on a dev box that left SECRET_KEY unset.
_DEV_FALLBACK_SECRET = "dev-secret-key-change-in-production"


def _deploy_secret() -> str | None:
    """The configured signing secret, or None when it is missing or the dev fallback."""
    secret = os.environ.get("DEPLOY_WEBHOOK_SECRET", "")
    if not secret or secret == _DEV_FALLBACK_SECRET:
        return None
    return secret


def _deploy_log() -> str:
    return os.environ.get(
        "DEPLOY_LOG_FILE",
        str(Path(__file__).parent.parent.parent.parent / "deploy-webhook.log"),
    )


def _log(outcome: str) -> None:
    """Append an attempt to the deploy log — outcome + caller, never the secret/signature."""
    line = f"{datetime.now(timezone.utc).isoformat()} {outcome} from={request.remote_addr}\n"
    with open(_deploy_log(), "a", encoding="utf-8") as fh:
        fh.write(line)


def _timestamp_fresh(raw_ts: str) -> bool:
    try:
        ts = int(raw_ts)
    except ValueError:
        return False
    return abs(time.time() - ts) <= _MAX_SKEW_SECONDS


@bp.post("/api/deploy/webhook")
def deploy_webhook() -> ResponseReturnValue:
    secret = _deploy_secret()
    if secret is None or os.environ.get("ENABLE_DEPLOY_WEBHOOK") != "1":
        # 404 (not 403) so a disabled deployment doesn't advertise the endpoint exists.
        return jsonify(error="Not found"), 404

    raw = request.get_data()
    timestamp = request.headers.get("X-Deploy-Timestamp", "")
    signature = request.headers.get("X-Deploy-Signature", "")

    if not _timestamp_fresh(timestamp):
        _log("stale-timestamp")
        return jsonify(error="Missing or stale timestamp"), 401

    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + raw, sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        _log("bad-signature")
        return jsonify(error="Bad signature"), 401

    # Detach the deploy from the request: start_new_session puts it in its own session
    # so an incidental worker recycle won't kill it mid-pip/mid-migrate, and the final
    # WSGI reload it triggers only ever truncates the cosmetic summary tail. Its
    # transcript (git/pip/migrate output) appends to the same deploy log.
    with open(_deploy_log(), "a", encoding="utf-8") as transcript:
        subprocess.Popen(
            ["bash", str(_SCRIPT_PATH)],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=transcript,
            stderr=subprocess.STDOUT,
            close_fds=True,
        )
    _log("accepted")
    return jsonify(status="accepted"), 202
