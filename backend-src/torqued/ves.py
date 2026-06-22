"""Client for the DVLA Vehicle Enquiry Service (VES) API.

Looks up a single vehicle by registration to read its road-tax status and due
date (DVLA also reports MOT status/expiry). Authenticates with a single API key
sent as `x-api-key` — no OAuth, unlike the DVSA MOT client in `torqued/mot.py`.

    VES_API_KEY   API key issued by DVLA, sent as x-api-key
    VES_API_URL   endpoint (optional; defaults to the live VES endpoint, can be
                  pointed at DVLA's UAT sandbox in dev/tests)
"""

import json
import os
import urllib.error
import urllib.request
from typing import Any

from torqued import mot

DEFAULT_API_URL = "https://driver-vehicle-licensing.api.gov.uk/vehicle-enquiry/v1/vehicles"
TIMEOUT = 15


class VesError(Exception):
    """A DVLA lookup failed; `status` is the HTTP status to relay."""

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


def _api_key() -> str:
    return os.environ.get("VES_API_KEY", "").strip()


def _api_url() -> str:
    return os.environ.get("VES_API_URL", "").strip() or DEFAULT_API_URL


def is_configured() -> bool:
    return bool(_api_key())


def fetch_vehicle(registration: str) -> dict[str, Any]:
    """Fetch the full DVLA VES record for a registration."""
    reg = mot.normalise_registration(registration)
    body = json.dumps({"registrationNumber": reg}).encode()
    req = urllib.request.Request(
        _api_url(),
        data=body,
        method="POST",
        headers={"x-api-key": _api_key(), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            result: dict[str, Any] = json.loads(resp.read().decode())
            return result
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise VesError(f"No DVLA record found for registration {reg}", 404) from e
        if e.code == 400:
            raise VesError(f"DVLA could not read registration {reg}", 400) from e
        raise VesError(f"DVLA API error: {e.code} {e.reason}") from e
    except Exception as e:
        raise VesError(f"Could not reach the DVLA API: {e}") from e
