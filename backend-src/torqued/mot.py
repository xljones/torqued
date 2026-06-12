"""Client for the DVSA MOT History API (https://documentation.history.mot.api.gov.uk/).

Authenticates with OAuth2 client credentials against Microsoft Entra ID and
calls the trade endpoint for a single vehicle by registration. Requires four
environment variables, issued by DVSA on registration:

    MOT_CLIENT_ID      OAuth2 client ID
    MOT_CLIENT_SECRET  OAuth2 client secret
    MOT_TOKEN_URL      https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token
    MOT_API_KEY        API key sent as X-API-Key
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_BASE = "https://history.mot.api.gov.uk/v1/trade/vehicles/registration/"
SCOPE = "https://tapi.dvsa.gov.uk/.default"
TIMEOUT = 15

# Access tokens last 60 minutes; cache one and renew a minute early.
_token_cache: dict[str, Any] = {"token": None, "expires": 0.0}


class MotError(Exception):
    """A DVSA lookup failed; `status` is the HTTP status to relay."""

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


def _config() -> dict[str, str]:
    return {
        key: os.environ.get(f"MOT_{key.upper()}", "").strip()
        for key in ("client_id", "client_secret", "token_url", "api_key")
    }


def is_configured() -> bool:
    return all(_config().values())


def normalise_registration(registration: str) -> str:
    return registration.replace(" ", "").upper()


def to_baseline(payload: dict[str, Any]) -> dict[str, Any]:
    """Map a raw DVSA vehicle payload onto Torqued's overridable detail fields.

    `year` is derived from whichever date the record provides when there's no
    explicit `manufactureYear`. Shared by the stored snapshot resolver and the
    live registration lookup so the mapping lives in exactly one place.
    """
    year = payload.get("manufactureYear")
    if year is None:
        for key in ("manufactureDate", "firstUsedDate", "registrationDate"):
            value = payload.get(key)
            if value and str(value)[:4].isdigit():
                year = int(str(value)[:4])
                break
    return {
        "make": payload.get("make"),
        "model": payload.get("model"),
        "year": year,
        "registration": payload.get("registration"),
        "colour": payload.get("primaryColour"),
        "fuel_type": payload.get("fuelType"),
        "engine_size": payload.get("engineSize"),
        "first_used_date": payload.get("firstUsedDate"),
        "registration_date": payload.get("registrationDate"),
    }


def _get_token() -> str:
    if _token_cache["token"] and time.time() < _token_cache["expires"]:
        return str(_token_cache["token"])
    cfg = _config()
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "scope": SCOPE,
    }).encode()
    req = urllib.request.Request(cfg["token_url"], data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise MotError(f"DVSA authentication failed: {e.code} {e.reason}") from e
    except Exception as e:
        raise MotError(f"Could not reach DVSA token endpoint: {e}") from e
    _token_cache["token"] = data["access_token"]
    _token_cache["expires"] = time.time() + int(data.get("expires_in", 3600)) - 60
    return str(_token_cache["token"])


def fetch_vehicle(registration: str) -> dict[str, Any]:
    """Fetch the full DVSA record (vehicle details + MOT tests) for a registration."""
    reg = normalise_registration(registration)
    req = urllib.request.Request(
        API_BASE + urllib.parse.quote(reg),
        headers={
            "Authorization": f"Bearer {_get_token()}",
            "X-API-Key": _config()["api_key"],
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            result: dict[str, Any] = json.loads(resp.read().decode())
            return result
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise MotError(f"No MOT record found for registration {reg}", 404) from e
        raise MotError(f"DVSA API error: {e.code} {e.reason}") from e
    except Exception as e:
        raise MotError(f"Could not reach the DVSA API: {e}") from e
