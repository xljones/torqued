"""Tests for /api/search: combined vehicle + service search."""
from flask.testing import FlaskClient

from tests.test_services import mk_service
from tests.test_vehicles import mk_vehicle


def test_search_matches_vehicles_and_services(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client, name="Street Triple", make="Triumph",
                   registration="LB21 XYZ")
    mk_service(auth_client, v["id"], title="Triple oil change")

    results = auth_client.get("/api/search?q=Triple").json
    types = {r["type"] for r in results}
    assert types == {"vehicle", "service"}


def test_search_by_registration(auth_client: FlaskClient) -> None:
    mk_vehicle(auth_client, registration="LB21 XYZ")
    results = auth_client.get("/api/search?q=LB21").json
    assert len(results) == 1
    assert results[0]["type"] == "vehicle"


def test_search_by_performer(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    mk_service(auth_client, v["id"], performed_by="A1 Garage")
    results = auth_client.get("/api/search?q=A1 Garage").json
    assert len(results) == 1
    assert results[0]["type"] == "service"


def test_search_no_results(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/search?q=nothinghere").json == []


def test_search_requires_auth(client: FlaskClient) -> None:
    assert client.get("/api/search?q=x").status_code == 401
