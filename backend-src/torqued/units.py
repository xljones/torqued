"""Unit conversions. Distances are stored canonically in km, pressures in psi."""

KM_PER_MILE = 1.609344
PSI_PER_BAR = 14.503773773


def to_km(value: float, unit: str) -> float:
    """Convert a distance in the given unit ('mi' or 'km') to km."""
    return value * KM_PER_MILE if unit == "mi" else value


def from_km(value_km: float, unit: str) -> float:
    """Convert a distance in km to the given unit ('mi' or 'km')."""
    return value_km / KM_PER_MILE if unit == "mi" else value_km


def parse_distance(
    d: dict, value_key: str = "odometer", unit_key: str = "odometer_unit"
) -> tuple[float | None, str]:
    """Read a distance + unit from a request payload; return (km, unit_entered).

    Raises ValueError if the value is present but not numeric, or the unit is unknown.
    """
    unit = d.get(unit_key) or "mi"
    if unit not in ("mi", "km"):
        raise ValueError(f"unknown distance unit: {unit}")
    raw = d.get(value_key)
    if raw is None or raw == "":
        return None, unit
    return to_km(float(raw), unit), unit
