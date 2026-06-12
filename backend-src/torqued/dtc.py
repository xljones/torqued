"""OBD-II diagnostic trouble code (DTC) lookup.

Descriptions come from the vendored dataset in data/obd_codes.json
(github.com/fabiovila/OBDIICodes, MIT licence) covering the SAE J2012
generic powertrain codes. For codes outside the dataset — typically
manufacturer-specific ones — we still decode the code's structure, which
is defined by the standard itself.
"""
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_PATH = Path(__file__).parent / "data" / "obd_codes.json"

CODE_RE = re.compile(r"^[PBCU][0-9][0-9A-F]{3}$")

_SYSTEMS = {
    "P": "Powertrain (engine, transmission, emissions)",
    "B": "Body (airbags, seatbelts, lighting, comfort)",
    "C": "Chassis (ABS, brakes, steering, suspension)",
    "U": "Network (CAN bus / module communication)",
}

# Second character: is the code SAE-standard ("generic") or manufacturer-specific?
# Per J2012: P0/P2/P34–P39 are generic, P1/P30–P33 manufacturer;
# B/C/U: 0 generic, 1–2 manufacturer, 3 reserved.
def _scope(code: str) -> str:
    system, digit = code[0], code[1]
    if system == "P":
        if digit in ("0", "2"):
            return "generic"
        if digit == "3":
            return "generic" if code[2] in "456789" else "manufacturer-specific"
        return "manufacturer-specific"
    return "generic" if digit == "0" else "manufacturer-specific"


_P_SUBSYSTEMS = {
    "1": "Fuel and air metering",
    "2": "Fuel and air metering (injector circuit)",
    "3": "Ignition system or misfire",
    "4": "Auxiliary emissions controls",
    "5": "Vehicle speed control and idle control",
    "6": "Computer output circuit",
    "7": "Transmission",
    "8": "Transmission",
    "9": "Transmission",
    "A": "Hybrid propulsion",
    "B": "Hybrid propulsion",
    "C": "Hybrid propulsion",
}


@lru_cache(maxsize=1)
def _codes() -> dict[str, str]:
    with open(_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def normalise(raw: str) -> str | None:
    """Uppercase and strip a user-entered code; return None if it isn't a valid DTC."""
    code = raw.strip().upper().replace(" ", "")
    return code if CODE_RE.match(code) else None


def lookup(raw: str) -> dict[str, Any] | None:
    """Return code details (description may be None for unknown codes), or None if malformed."""
    code = normalise(raw)
    if code is None:
        return None
    subsystem = _P_SUBSYSTEMS.get(code[2]) if code[0] == "P" else None
    return {
        "code": code,
        "description": _codes().get(code),
        "system": _SYSTEMS[code[0]],
        "scope": _scope(code),
        "subsystem": subsystem,
    }


def list_all() -> list[dict[str, str]]:
    """Return every known code as {code, description}, in dataset order."""
    return [{"code": code, "description": description} for code, description in _codes().items()]


def search(query: str, limit: int = 25) -> list[dict[str, str]]:
    """Return codes whose code or description contains the query, capped at limit."""
    q = query.strip().lower()
    if not q:
        return []
    results = []
    for code, description in _codes().items():
        if q in code.lower() or q in description.lower():
            results.append({"code": code, "description": description})
            if len(results) >= limit:
                break
    return results
