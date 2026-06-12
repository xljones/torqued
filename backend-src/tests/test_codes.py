"""Tests for /api/codes: OBD-II diagnostic trouble code lookup."""
from flask.testing import FlaskClient

from torqued import dtc


def test_lookup_known_code(auth_client: FlaskClient) -> None:
    r = auth_client.get("/api/codes/P0016")
    assert r.status_code == 200
    assert r.json["code"] == "P0016"
    assert "Crankshaft Position - Camshaft Position Correlation" in r.json["description"]
    assert r.json["scope"] == "generic"
    assert r.json["system"].startswith("Powertrain")
    assert r.json["subsystem"] is None  # third char 0 has no subsystem mapping


def test_lookup_normalises_input(auth_client: FlaskClient) -> None:
    r = auth_client.get("/api/codes/p0300 ")
    assert r.status_code == 200
    assert r.json["code"] == "P0300"
    assert r.json["description"] == "Random/Multiple Cylinder Misfire Detected"
    assert r.json["subsystem"] == "Ignition system or misfire"


def test_lookup_unknown_but_valid_code(auth_client: FlaskClient) -> None:
    """Manufacturer-specific codes aren't in the generic dataset but still decode."""
    r = auth_client.get("/api/codes/U0100")
    assert r.status_code == 200
    assert r.json["description"] is None
    assert r.json["system"].startswith("Network")
    assert r.json["scope"] == "generic"

    r = auth_client.get("/api/codes/B1234")
    assert r.json["scope"] == "manufacturer-specific"
    assert r.json["system"].startswith("Body")


def test_lookup_p1_is_manufacturer_specific(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/codes/P1101").json["scope"] == "manufacturer-specific"


def test_lookup_p3_scope_split(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/codes/P3100").json["scope"] == "manufacturer-specific"
    assert auth_client.get("/api/codes/P3400").json["scope"] == "generic"


def test_lookup_invalid_code(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/codes/XYZ").status_code == 400
    assert auth_client.get("/api/codes/P00161").status_code == 400


def test_search_by_keyword(auth_client: FlaskClient) -> None:
    r = auth_client.get("/api/codes?q=misfire")
    assert r.status_code == 200
    assert any(m["code"] == "P0300" for m in r.json)
    assert len(r.json) <= 25


def test_search_by_code_fragment(auth_client: FlaskClient) -> None:
    r = auth_client.get("/api/codes?q=P042")
    assert any(m["code"] == "P0420" for m in r.json)


def test_search_caps_results(auth_client: FlaskClient) -> None:
    r = auth_client.get("/api/codes?q=circuit")
    assert len(r.json) == 25


def test_empty_query_lists_all_codes(auth_client: FlaskClient) -> None:
    """No query (the pre-search browse state) returns the full code list, not []."""
    r = auth_client.get("/api/codes")
    assert r.status_code == 200
    assert len(r.json) == len(dtc._codes())
    assert any(m["code"] == "P0016" for m in r.json)


def test_blank_query_lists_all_codes(auth_client: FlaskClient) -> None:
    assert len(auth_client.get("/api/codes?q=%20").json) == len(dtc._codes())


def test_search_with_empty_query_returns_empty() -> None:
    assert dtc.search("  ") == []


def test_list_all_returns_every_code() -> None:
    rows = dtc.list_all()
    assert len(rows) == len(dtc._codes())
    assert {"code": "P0300", "description": "Random/Multiple Cylinder Misfire Detected"} in rows


def test_lookup_requires_auth(client: FlaskClient) -> None:
    assert client.get("/api/codes/P0016").status_code == 401


def test_dataset_integrity() -> None:
    """Every vendored code parses and has a description."""
    codes = dtc._codes()
    assert len(codes) > 2000
    for code, description in codes.items():
        assert dtc.normalise(code) == code
        assert description.strip()
