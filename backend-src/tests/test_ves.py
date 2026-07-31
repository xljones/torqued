"""Tests for the DVLA VES integration: scraper client, storage, routes, reminders."""
import json
import urllib.error
from datetime import date, timedelta
from typing import Any

import pytest
from flask.testing import FlaskClient

from tests.test_vehicles import mk_vehicle
from torqued import ves

# The gov.uk home page carries two `authenticity_token` inputs — the cookie-consent
# form and the vehicle-enquiry form. Only the latter is the right one.
HOME_HTML = """
<html><body>
  <form action="/cookies" method="post">
    <input type="hidden" name="authenticity_token" value="CONSENT-TOKEN">
  </form>
  <form action="/vehicle-enquiry/save?locale=en" method="post">
    <input type="hidden" name="authenticity_token" value="HOME-TOKEN">
    <input name="wizard_vehicle_enquiry_capture_vrn[vrn]">
  </form>
</body></html>
"""

CONFIRM_HTML = """
<html><body>
  <form action="/vehicle-enquiry/save?locale=en" method="post">
    <input type="hidden" name="authenticity_token" value="CONFIRM-TOKEN">
    <input name="wizard_vehicle_enquiry_capture_confirm_vehicle[confirmed]">
  </form>
</body></html>
"""

# The vehicle-profile summary rows on the result page (id -> displayed value), mirroring
# the real markup fetch_ves reads with _field(..., value_tag="dd").
_PROFILE_ROWS = {
    "make": "FORD",
    "colour": "Blue",
    "date_of_first_registration": "October 2003",
    "year_of_manufacture": "2003",
    "engine_capacity": "1781 cc",
    "co2_emissions": "204 g/km",
    "fuel_type": "PETROL",
    "euro_status": "Not available",
    "real_driving_emissions": "Not available",
    "marked_for_export": "No",
    "type_approval": "M1",
    "wheelPlan": "2 AXLE RIGID BODY",
    "revenue_weight": "Not available",
    "date_of_last_v5c_issued": "7 June 2023",
}


def found_html(status: str = "Taxed", due: str = "Tax due: 1 December 2026",
               mot: str | None = "has a valid MOT certificate",
               mot_expiry: str | None = "Expires: 11 June 2027") -> str:
    # Mirrors the real gov.uk result page: each field is a summary row keyed by id that
    # wraps a <dt> label and the <dd> value. The MOT panel carries a visually-hidden status
    # sentence (id=mot_hidden_details) and the expiry; pass mot=None to model a vehicle with
    # no MOT record (panel absent).
    mot_panel = "" if mot is None else f"""
      <div id="mot-status-panel">
        <h2><span aria-hidden="true">MOT</span>
          <span class="govuk-visually-hidden" id="mot_hidden_details">Vehicle {mot}</span></h2>
        <p>{mot_expiry or ''}</p>
      </div>"""
    rows = "".join(
        f'<div class="govuk-summary-list__row" id="{rid}"><dt>{rid}</dt><dd>{val}</dd></div>'
        for rid, val in _PROFILE_ROWS.items()
    )
    return f"""
    <html><body>
      <div id="tax-status-panel">
        <h2><span aria-hidden="true">{status}</span></h2>
        <p>{due}<br>keep it insured</p>
      </div>
      {mot_panel}
      <dl class="govuk-summary-list">
        <div class="govuk-summary-list__row" id="vehicleStatus"><dt>Vehicle status</dt><dd>{status}</dd></div>
        {rows}
      </dl>
    </body></html>
    """


def make_fake_request(*, found: str | None = None, not_found: bool = False):
    """A stand-in for ves._request that walks the wizard without any network."""
    page = found if found is not None else found_html()

    def fake(opener: Any, url: str, fields: dict[str, str] | None = None) -> tuple[str, str]:
        if fields is None:
            return HOME_HTML, ves.BASE_URL + "/"
        if "wizard_vehicle_enquiry_capture_vrn[vrn]" in fields:
            if not_found:
                return "", ves.BASE_URL + "/VehicleNotFound?locale=en"
            return CONFIRM_HTML, ves.BASE_URL + "/ConfirmVehicle?locale=en"
        return page, ves.BASE_URL + "/VehicleFound?locale=en"

    return fake


def _forbid_request(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("relay path must not call the direct scraper (_request)")


@pytest.fixture(autouse=True)
def _no_relay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default every test to the direct-scrape path; relay tests opt in with VES_RELAY_URL."""
    monkeypatch.delenv("VES_RELAY_URL", raising=False)
    monkeypatch.delenv("VES_RELAY_TOKEN", raising=False)


# ── fake HTTP plumbing (covers _request) ───────────────────────────────────────

class FakeResponse:
    def __init__(self, body: str, url: str) -> None:
        self._body, self._url = body, url

    def read(self) -> bytes:
        return self._body.encode()

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: Any) -> bool:
        return False


class FakeOpener:
    def __init__(self, resp: Any = None, exc: Exception | None = None) -> None:
        self._resp, self._exc = resp, exc

    def open(self, req: Any, timeout: int = 0) -> Any:
        if self._exc:
            raise self._exc
        return self._resp


def test_request_success() -> None:
    opener = FakeOpener(FakeResponse("<html>hi</html>", "https://x/final"))
    html, url = ves._request(opener, "https://x/")
    assert html == "<html>hi</html>"
    assert url == "https://x/final"


def test_request_http_error() -> None:
    opener = FakeOpener(exc=urllib.error.HTTPError("u", 500, "err", None, None))  # type: ignore[arg-type]
    with pytest.raises(ves.VesError) as e:
        ves._request(opener, "https://x/")
    assert e.value.status == 502


def test_request_network_error() -> None:
    opener = FakeOpener(exc=OSError("no route"))
    with pytest.raises(ves.VesError) as e:
        ves._request(opener, "https://x/", {"a": "b"})
    assert e.value.status == 502


# ── client parsing helpers ──────────────────────────────────────────────────────

def test_effective_endpoint_direct_and_relay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VES_RELAY_URL", raising=False)
    assert ves.effective_endpoint() == {"mode": "direct", "url": ves.BASE_URL}
    monkeypatch.setenv("VES_RELAY_URL", "https://relay.example/")
    assert ves.effective_endpoint() == {"mode": "relay", "url": "https://relay.example/"}


def test_normalise_registration() -> None:
    assert ves.normalise_registration("a1 xyz") == "A1XYZ"


def test_extract_token_picks_the_save_form() -> None:
    assert ves._extract_token(HOME_HTML) == "HOME-TOKEN"


def test_extract_token_missing() -> None:
    with pytest.raises(ves.VesError) as e:
        ves._extract_token("<html><form action='/other'></form></html>")
    assert e.value.status == 502


def test_field_reads_element_and_handles_missing() -> None:
    row = "<div id='vehicleStatus'><dt>Vehicle status</dt> <dd>Taxed</dd></div>"
    # value_tag='dd' keeps only the value, dropping the <dt> label.
    assert ves._field(row, "vehicleStatus", value_tag="dd") == "Taxed"
    assert ves._field(row, "nope", value_tag="dd") is None
    # Without value_tag the whole element is read (used for the tax panel + date regex).
    assert ves._field(row, "vehicleStatus") == "Vehicle status Taxed"


def test_parse_due_date_variants() -> None:
    assert ves._parse_due_date("Tax due: 1 December 2026") == "2026-12-01"
    assert ves._parse_due_date(None) is None
    assert ves._parse_due_date("no date here") is None
    assert ves._parse_due_date("5 Smarch 2026") is None       # unknown month name
    assert ves._parse_due_date("31 February 2026") is None     # invalid calendar date


# ── fetch_ves flow ──────────────────────────────────────────────────────────────

def test_fetch_ves_full_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ves, "_request", make_fake_request())
    result = ves.fetch_ves("a1 xyz")
    assert result == {
        "registration": "A1XYZ",
        "tax_status": "Taxed",
        "tax_due_date": "2026-12-01",
        "mot_status": "Vehicle has a valid MOT certificate",
        "mot_expiry_date": "2027-06-11",
        "make": "FORD",
        "colour": "Blue",
        "date_of_first_registration": "October 2003",
        "year_of_manufacture": "2003",
        "cylinder_capacity": "1781 cc",
        "co2_emissions": "204 g/km",
        "fuel_type": "PETROL",
        "euro_status": "Not available",
        "real_driving_emissions": "Not available",
        "export_marker": "No",
        "type_approval": "M1",
        "wheelplan": "2 AXLE RIGID BODY",
        "revenue_weight": "Not available",
        "date_of_last_v5c": "7 June 2023",
    }


def test_fetch_ves_sorn_has_no_due_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ves, "_request", make_fake_request(found=found_html(status="SORN", due="")))
    result = ves.fetch_ves("A1XYZ")
    assert result["tax_status"] == "SORN"
    assert result["tax_due_date"] is None


def test_fetch_ves_captures_mot_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ves, "_request", make_fake_request())
    result = ves.fetch_ves("A1XYZ")
    assert result["mot_status"] == "Vehicle has a valid MOT certificate"
    assert result["mot_expiry_date"] == "2027-06-11"


def test_fetch_ves_no_mot_panel_is_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    # A vehicle with no MOT record has no panel — the lookup still succeeds.
    monkeypatch.setattr(ves, "_request", make_fake_request(found=found_html(mot=None)))
    result = ves.fetch_ves("A1XYZ")
    assert result["tax_status"] == "Taxed"
    assert result["mot_status"] is None
    assert result["mot_expiry_date"] is None


def test_fetch_ves_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ves, "_request", make_fake_request(not_found=True))
    with pytest.raises(ves.VesError) as e:
        ves.fetch_ves("ZZ99ZZZ")
    assert e.value.status == 404


def test_fetch_ves_unexpected_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(opener: Any, url: str, fields: dict[str, str] | None = None) -> tuple[str, str]:
        if fields is None:
            return HOME_HTML, ves.BASE_URL + "/"
        if "wizard_vehicle_enquiry_capture_vrn[vrn]" in fields:
            return CONFIRM_HTML, ves.BASE_URL + "/ConfirmVehicle"
        return "<html></html>", ves.BASE_URL + "/"  # not the VehicleFound page

    monkeypatch.setattr(ves, "_request", fake)
    with pytest.raises(ves.VesError) as e:
        ves.fetch_ves("A1XYZ")
    assert e.value.status == 502


def test_fetch_ves_missing_status(monkeypatch: pytest.MonkeyPatch) -> None:
    no_status = "<html><body><div id='tax-status-panel'>Taxed</div></body></html>"
    monkeypatch.setattr(ves, "_request", make_fake_request(found=no_status))
    with pytest.raises(ves.VesError) as e:
        ves.fetch_ves("A1XYZ")
    assert e.value.status == 502


# ── fetch_ves via the relay (VES_RELAY_URL) ──────────────────────────────────────

def _relay_urlopen(*, payload: dict[str, Any] | None = None, exc: Exception | None = None,
                   captured: dict[str, Any] | None = None):
    """A stand-in for urllib.request.urlopen used by the relay path."""
    def fake(req: Any, timeout: int = 0) -> Any:
        if captured is not None:
            captured["url"] = req.full_url
            captured["auth"] = req.get_header("Authorization")
        if exc is not None:
            raise exc
        return FakeResponse(json.dumps(payload), req.full_url)

    return fake


def test_fetch_ves_via_relay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VES_RELAY_URL", "https://relay.example/")
    monkeypatch.setenv("VES_RELAY_TOKEN", "s3cret")
    payload = {"registration": "A1XYZ", "tax_status": "Taxed", "tax_due_date": "2026-12-01",
               "mot_status": "Vehicle has a valid MOT certificate", "mot_expiry_date": "2027-06-11",
               "make": "FORD", "colour": "Blue", "cylinder_capacity": "1781 cc"}
    captured: dict[str, Any] = {}
    # The relay path must never touch the direct scraper.
    monkeypatch.setattr(ves, "_request", _forbid_request)
    monkeypatch.setattr(ves.urllib.request, "urlopen",
                        _relay_urlopen(payload=payload, captured=captured))
    assert ves.fetch_ves("a1 xyz") == payload
    assert captured["url"] == "https://relay.example/ves/A1XYZ"
    assert captured["auth"] == "Bearer s3cret"


def test_fetch_ves_via_relay_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VES_RELAY_URL", "https://relay.example")
    captured: dict[str, Any] = {}
    payload = {"registration": "A1XYZ", "tax_status": "SORN", "tax_due_date": None}
    monkeypatch.setattr(ves.urllib.request, "urlopen",
                        _relay_urlopen(payload=payload, captured=captured))
    assert ves.fetch_ves("A1XYZ")["tax_status"] == "SORN"
    assert captured["auth"] is None


def test_fetch_ves_via_relay_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VES_RELAY_URL", "https://relay.example")
    exc = urllib.error.HTTPError("u", 404, "Not Found", None, None)  # type: ignore[arg-type]
    monkeypatch.setattr(ves.urllib.request, "urlopen", _relay_urlopen(exc=exc))
    with pytest.raises(ves.VesError) as e:
        ves.fetch_ves("ZZ99ZZZ")
    assert e.value.status == 404


def test_fetch_ves_via_relay_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VES_RELAY_URL", "https://relay.example")
    exc = urllib.error.HTTPError("u", 500, "Server Error", None, None)  # type: ignore[arg-type]
    monkeypatch.setattr(ves.urllib.request, "urlopen", _relay_urlopen(exc=exc))
    with pytest.raises(ves.VesError) as e:
        ves.fetch_ves("A1XYZ")
    assert e.value.status == 502
    assert "VES relay error" in str(e.value)


def test_fetch_ves_via_relay_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VES_RELAY_URL", "https://relay.example")
    monkeypatch.setattr(ves.urllib.request, "urlopen",
                        _relay_urlopen(exc=urllib.error.URLError("boom")))
    with pytest.raises(ves.VesError) as e:
        ves.fetch_ves("A1XYZ")
    assert e.value.status == 502
    assert "Could not reach the VES relay" in str(e.value)


# ── routes ──────────────────────────────────────────────────────────────────────

def test_ves_status(auth_client: FlaskClient) -> None:
    # VES is a credential-less scrape, so it always reports configured.
    assert auth_client.get("/api/ves/status").json == {"configured": True}


def test_get_ves_requires_auth(client: FlaskClient) -> None:
    assert client.get("/api/vehicles/1/ves").status_code == 401


def test_get_ves_vehicle_404(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/vehicles/999/ves").status_code == 404


def test_get_ves_empty(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client, registration="A1 XYZ")
    r = auth_client.get(f"/api/vehicles/{v['id']}/ves")
    assert r.status_code == 200
    assert r.json == {"configured": True, "ves": None}


def test_refresh_ves_vehicle_404(auth_client: FlaskClient) -> None:
    assert auth_client.post("/api/vehicles/999/ves/refresh").status_code == 404


def test_refresh_ves_readonly_403(readonly_client: FlaskClient, garage: dict[str, Any]) -> None:
    from torqued.db import get_db
    from torqued.repositories.vehicle_repository import VehicleRepository

    with get_db() as db:
        v = VehicleRepository(db).create(garage["id"], {"name": "Shared bike"})
    assert readonly_client.post(f"/api/vehicles/{v['id']}/ves/refresh").status_code == 403


def test_refresh_ves_without_registration(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    r = auth_client.post(f"/api/vehicles/{v['id']}/ves/refresh")
    assert r.status_code == 400
    assert "registration" in r.json["error"]


def test_refresh_ves_relays_error(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(reg: str) -> dict[str, Any]:
        raise ves.VesError("No vehicle found for registration ZZ99ZZZ", 404)

    monkeypatch.setattr(ves, "fetch_ves", boom)
    v = mk_vehicle(auth_client, registration="ZZ99 ZZZ")
    r = auth_client.post(f"/api/vehicles/{v['id']}/ves/refresh")
    assert r.status_code == 404
    assert "No vehicle found" in r.json["error"]


def test_refresh_ves_stores_and_gets(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"registration": "A1XYZ", "tax_status": "Taxed", "tax_due_date": "2026-12-01",
               "mot_status": "Vehicle has a valid MOT certificate", "mot_expiry_date": "2027-06-11",
               "make": "FORD", "colour": "Blue", "cylinder_capacity": "1781 cc"}
    monkeypatch.setattr(ves, "fetch_ves", lambda reg: payload)
    v = mk_vehicle(auth_client, registration="A1 XYZ")

    r = auth_client.post(f"/api/vehicles/{v['id']}/ves/refresh")
    assert r.status_code == 200
    assert r.json["configured"] is True
    snap = r.json["ves"]
    assert snap["tax_status"] == "Taxed"
    assert snap["tax_due_date"] == "2026-12-01"
    assert snap["mot_expiry_date"] == "2027-06-11"
    # One record holds the whole VES payload verbatim in raw — tax, MOT and the profile.
    assert snap["raw"]["make"] == "FORD"
    assert snap["raw"]["mot_status"] == "Vehicle has a valid MOT certificate"
    assert snap["raw"]["cylinder_capacity"] == "1781 cc"

    g = auth_client.get(f"/api/vehicles/{v['id']}/ves")
    assert g.json["ves"]["registration"] == "A1XYZ"


def test_disconnect_clears_ves(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"registration": "A1XYZ", "tax_status": "Taxed", "tax_due_date": "2026-12-01"}
    monkeypatch.setattr(ves, "fetch_ves", lambda reg: payload)
    v = mk_vehicle(auth_client, registration="A1 XYZ")
    auth_client.post(f"/api/vehicles/{v['id']}/ves/refresh")
    assert auth_client.get(f"/api/vehicles/{v['id']}/ves").json["ves"] is not None

    body = {"name": v["name"], "kind": v["kind"], "registration": "B2 YYY", "disconnect_mot": True}
    assert auth_client.put(f"/api/vehicles/{v['id']}", json=body).status_code == 200
    assert auth_client.get(f"/api/vehicles/{v['id']}/ves").json["ves"] is None


# ── record retention & relink (parity with DVSA, migration 0007) ─────────────────

VES_PAYLOAD = {"registration": "A1XYZ", "tax_status": "Taxed", "tax_due_date": "2026-12-01",
               "mot_status": "Vehicle has a valid MOT certificate", "mot_expiry_date": "2027-06-11",
               "make": "FORD", "colour": "Blue"}


def test_ves_refresh_keeps_previous_lookup_as_history(garage: dict[str, Any]) -> None:
    """A VES refresh retains the prior lookup (detached), not deletes it."""
    from sqlalchemy import select

    from torqued.db import get_db
    from torqued.models import VehicleVes
    from torqued.repositories.ves_repository import VesRepository
    from torqued.repositories.vehicle_repository import VehicleRepository

    with get_db() as db:
        v = VehicleRepository(db).create(garage["id"], {"name": "Car"})
        VesRepository(db).replace_for_vehicle(v["id"], VES_PAYLOAD)
    with get_db() as db:
        VesRepository(db).replace_for_vehicle(v["id"], VES_PAYLOAD)

    with get_db() as db:
        rows = db.scalars(select(VehicleVes).order_by(VehicleVes.id)).all()
        assert len(rows) == 2  # both lookups kept
        assert [r.vehicle_id for r in rows] == [None, v["id"]]  # older detached, newer live
        assert VesRepository(db).get_for_vehicle(v["id"]) is not None


def test_ves_record_retained_after_vehicle_delete(garage: dict[str, Any]) -> None:
    from sqlalchemy import select

    from torqued.db import get_db
    from torqued.models import VehicleVes
    from torqued.repositories.ves_repository import VesRepository
    from torqued.repositories.vehicle_repository import VehicleRepository

    with get_db() as db:
        v = VehicleRepository(db).create(garage["id"], {"name": "Doomed"})
        VesRepository(db).replace_for_vehicle(v["id"], {**VES_PAYLOAD, "registration": "OLD123"})
    with get_db() as db:
        assert VehicleRepository(db).delete(v["id"]) is True
        # The record survives detached (vehicle_id NULL), not cascaded away.
        assert VesRepository(db).get_for_vehicle(v["id"]) is None
        row = db.scalars(select(VehicleVes)).one()
        assert row.vehicle_id is None
        assert row.registration == "OLD123"


def test_standalone_ves_lookup_links_when_vehicle_added_later(
    auth_client: FlaskClient, garage: dict[str, Any]
) -> None:
    from torqued.db import get_db
    from torqued.repositories.ves_repository import VesRepository

    with get_db() as db:
        VesRepository(db).store_detached_lookup(VES_PAYLOAD)

    # Adding a vehicle on that plate ties the standalone record to it.
    v = mk_vehicle(auth_client, registration="A1 XYZ")
    with get_db() as db:
        linked = VesRepository(db).get_for_vehicle(v["id"])
    assert linked is not None
    assert linked["tax_status"] == "Taxed"
    assert linked["mot_expiry_date"] == "2027-06-11"


def test_ves_relink_noop_without_registration(
    auth_client: FlaskClient, garage: dict[str, Any]
) -> None:
    from torqued.db import get_db
    from torqued.repositories.ves_repository import VesRepository

    v = mk_vehicle(auth_client, registration="ZZ99 ZZZ")
    with get_db() as db:
        assert VesRepository(db).relink_detached(v["id"], "   ") is False
        assert VesRepository(db).get_for_vehicle(v["id"]) is None


# ── tax reminders (derived from the VES record) ──────────────────────────────────

def _store_ves(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> dict[str, Any]:
    monkeypatch.setattr(ves, "fetch_ves", lambda reg: payload)
    v = mk_vehicle(auth_client, registration=payload["registration"])
    r = auth_client.post(f"/api/vehicles/{v['id']}/ves/refresh")
    assert r.status_code == 200, r.json
    return v


def _tax_reminders(auth_client: FlaskClient) -> list[dict[str, Any]]:
    return [r for r in auth_client.get("/api/reminders").json if r["type"] == "tax"]


def test_tax_reminder_due_soon(auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    due = (date.today() + timedelta(days=20)).isoformat()
    v = _store_ves(auth_client, monkeypatch,
                   {"registration": "A1XYZ", "tax_status": "Taxed", "tax_due_date": due})
    [rem] = _tax_reminders(auth_client)
    assert rem["status"] == "due_soon"
    assert rem["title"] == "Road tax"
    assert rem["category"] == "Tax"
    assert rem["next_due_date"] == due
    assert rem["vehicle_id"] == v["id"]
    detail = auth_client.get(f"/api/vehicles/{v['id']}").json
    assert [r["status"] for r in detail["reminders"] if r["type"] == "tax"] == ["due_soon"]


def test_tax_reminder_overdue(auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    due = (date.today() - timedelta(days=5)).isoformat()
    _store_ves(auth_client, monkeypatch,
               {"registration": "A1XYZ", "tax_status": "Untaxed", "tax_due_date": due})
    [rem] = _tax_reminders(auth_client)
    assert rem["status"] == "overdue"


def test_tax_reminder_outside_window_hidden(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    due = (date.today() + timedelta(days=120)).isoformat()
    _store_ves(auth_client, monkeypatch,
               {"registration": "A1XYZ", "tax_status": "Taxed", "tax_due_date": due})
    assert _tax_reminders(auth_client) == []


def test_tax_reminder_sorn_hidden(auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _store_ves(auth_client, monkeypatch,
               {"registration": "A1XYZ", "tax_status": "SORN", "tax_due_date": None})
    assert _tax_reminders(auth_client) == []


def test_tax_reminder_excludes_archived(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    due = (date.today() + timedelta(days=20)).isoformat()
    v = _store_ves(auth_client, monkeypatch,
                   {"registration": "A1XYZ", "tax_status": "Taxed", "tax_due_date": due})
    auth_client.put(f"/api/vehicles/{v['id']}", json={"name": v["name"], "archived": True})
    assert _tax_reminders(auth_client) == []


def test_tax_reminders_empty_garages() -> None:
    from torqued.db import get_db
    from torqued.repositories.ves_repository import VesRepository

    with get_db() as db:
        assert VesRepository(db).reminders([]) == []


# ── tax summaries (vehicle list cards) ──────────────────────────────────────────

def test_vehicle_list_includes_tax_summary(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"registration": "A1XYZ", "tax_status": "Taxed", "tax_due_date": "2026-12-01"}
    monkeypatch.setattr(ves, "fetch_ves", lambda reg: payload)
    v = mk_vehicle(auth_client, registration="A1 XYZ")
    auth_client.post(f"/api/vehicles/{v['id']}/ves/refresh")
    row = next(x for x in auth_client.get("/api/vehicles").json if x["id"] == v["id"])
    assert row["tax_summary"] == {"tax_status": "Taxed", "tax_due_date": "2026-12-01"}


def test_tax_summaries_empty() -> None:
    from torqued.db import get_db
    from torqued.repositories.vehicle_repository import VehicleRepository

    with get_db() as db:
        assert VehicleRepository(db).tax_summaries([]) == {}
