"""Tests for torqued/units.py: distance conversion helpers."""
import pytest

from torqued.units import KM_PER_MILE, from_km, parse_distance, to_km


def test_to_km_from_miles() -> None:
    assert to_km(100, "mi") == pytest.approx(160.9344)


def test_to_km_passthrough() -> None:
    assert to_km(100, "km") == 100


def test_from_km_to_miles() -> None:
    assert from_km(KM_PER_MILE, "mi") == pytest.approx(1.0)


def test_from_km_passthrough() -> None:
    assert from_km(42.0, "km") == 42.0


def test_parse_distance_default_unit() -> None:
    km, unit = parse_distance({"odometer": 100})
    assert unit == "mi"
    assert km == pytest.approx(160.9344)


def test_parse_distance_km() -> None:
    km, unit = parse_distance({"odometer": "250", "odometer_unit": "km"})
    assert unit == "km"
    assert km == 250.0


def test_parse_distance_missing_value() -> None:
    assert parse_distance({}) == (None, "mi")
    assert parse_distance({"odometer": ""}) == (None, "mi")


def test_parse_distance_bad_unit() -> None:
    with pytest.raises(ValueError, match="unknown distance unit"):
        parse_distance({"odometer": 1, "odometer_unit": "furlongs"})


def test_parse_distance_non_numeric() -> None:
    with pytest.raises(ValueError):
        parse_distance({"odometer": "lots"})


def test_parse_distance_custom_key() -> None:
    km, _ = parse_distance({"next_due_distance": 10, "odometer_unit": "km"},
                           value_key="next_due_distance")
    assert km == 10.0
