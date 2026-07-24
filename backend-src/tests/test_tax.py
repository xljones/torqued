"""Tests for the road-tax / SORN integration: scraper client, storage, and routes."""
import urllib.error
from datetime import date, timedelta
from typing import Any

import pytest
from flask.testing import FlaskClient

from tests.test_vehicles import mk_vehicle
from torqued import tax

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


def found_html(status: str = "Taxed", due: str = "Tax due: 1 December 2026",
               make: str = "FORD", colour: str = "Blue") -> str:
    # Mirrors the real gov.uk result page: each field is a summary row keyed by id that
    # wraps both a <dt> label and the <dd> value.
    return f"""
    <html><body>
      <div id="tax-status-panel">
        <h2><span aria-hidden="true">{status}</span></h2>
        <p>{due}<br>keep it insured</p>
      </div>
      <div id="mot-status-panel"><h2>MOT</h2><p>Expires: 11 June 2027</p></div>
      <dl class="govuk-summary-list">
        <div class="govuk-summary-list__row" id="vehicleStatus"><dt>Vehicle status</dt><dd>{status}</dd></div>
        <div class="govuk-summary-list__row" id="make"><dt>Vehicle make</dt><dd>{make}</dd></div>
        <div class="govuk-summary-list__row" id="colour"><dt>Vehicle colour</dt><dd>{colour}</dd></div>
      </dl>
    </body></html>
    """


def make_fake_request(*, found: str | None = None, not_found: bool = False):
    """A stand-in for tax._request that walks the wizard without any network."""
    page = found if found is not None else found_html()

    def fake(opener: Any, url: str, fields: dict[str, str] | None = None) -> tuple[str, str]:
        if fields is None:
            return HOME_HTML, tax.BASE_URL + "/"
        if "wizard_vehicle_enquiry_capture_vrn[vrn]" in fields:
            if not_found:
                return "", tax.BASE_URL + "/VehicleNotFound?locale=en"
            return CONFIRM_HTML, tax.BASE_URL + "/ConfirmVehicle?locale=en"
        return page, tax.BASE_URL + "/VehicleFound?locale=en"

    return fake


@pytest.fixture
def tax_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the default 'enabled' state regardless of ambient VES_SCRAPE_ENABLED."""
    monkeypatch.delenv("VES_SCRAPE_ENABLED", raising=False)


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
    html, url = tax._request(opener, "https://x/")
    assert html == "<html>hi</html>"
    assert url == "https://x/final"


def test_request_http_error() -> None:
    opener = FakeOpener(exc=urllib.error.HTTPError("u", 500, "err", None, None))  # type: ignore[arg-type]
    with pytest.raises(tax.TaxError) as e:
        tax._request(opener, "https://x/")
    assert e.value.status == 502


def test_request_network_error() -> None:
    opener = FakeOpener(exc=OSError("no route"))
    with pytest.raises(tax.TaxError) as e:
        tax._request(opener, "https://x/", {"a": "b"})
    assert e.value.status == 502


# ── client parsing helpers ──────────────────────────────────────────────────────

def test_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VES_SCRAPE_ENABLED", raising=False)
    assert tax.is_configured() is True
    monkeypatch.setenv("VES_SCRAPE_ENABLED", "0")
    assert tax.is_configured() is False


def test_normalise_registration() -> None:
    assert tax.normalise_registration("a1 xyz") == "A1XYZ"


def test_extract_token_picks_the_save_form() -> None:
    assert tax._extract_token(HOME_HTML) == "HOME-TOKEN"


def test_extract_token_missing() -> None:
    with pytest.raises(tax.TaxError) as e:
        tax._extract_token("<html><form action='/other'></form></html>")
    assert e.value.status == 502


def test_field_reads_element_and_handles_missing() -> None:
    row = "<div id='vehicleStatus'><dt>Vehicle status</dt> <dd>Taxed</dd></div>"
    # value_tag='dd' keeps only the value, dropping the <dt> label.
    assert tax._field(row, "vehicleStatus", value_tag="dd") == "Taxed"
    assert tax._field(row, "nope", value_tag="dd") is None
    # Without value_tag the whole element is read (used for the tax panel + date regex).
    assert tax._field(row, "vehicleStatus") == "Vehicle status Taxed"


def test_parse_due_date_variants() -> None:
    assert tax._parse_due_date("Tax due: 1 December 2026") == "2026-12-01"
    assert tax._parse_due_date(None) is None
    assert tax._parse_due_date("no date here") is None
    assert tax._parse_due_date("5 Smarch 2026") is None       # unknown month name
    assert tax._parse_due_date("31 February 2026") is None     # invalid calendar date


# ── fetch_tax flow ──────────────────────────────────────────────────────────────

def test_fetch_tax_taxed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tax, "_request", make_fake_request())
    result = tax.fetch_tax("a1 xyz")
    assert result == {
        "registration": "A1XYZ",
        "tax_status": "Taxed",
        "tax_due_date": "2026-12-01",
        "make": "FORD",
        "colour": "Blue",
    }


def test_fetch_tax_sorn_has_no_due_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tax, "_request", make_fake_request(found=found_html(status="SORN", due="")))
    result = tax.fetch_tax("A1XYZ")
    assert result["tax_status"] == "SORN"
    assert result["tax_due_date"] is None


def test_fetch_tax_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tax, "_request", make_fake_request(not_found=True))
    with pytest.raises(tax.TaxError) as e:
        tax.fetch_tax("ZZ99ZZZ")
    assert e.value.status == 404


def test_fetch_tax_unexpected_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(opener: Any, url: str, fields: dict[str, str] | None = None) -> tuple[str, str]:
        if fields is None:
            return HOME_HTML, tax.BASE_URL + "/"
        if "wizard_vehicle_enquiry_capture_vrn[vrn]" in fields:
            return CONFIRM_HTML, tax.BASE_URL + "/ConfirmVehicle"
        return "<html></html>", tax.BASE_URL + "/"  # not the VehicleFound page

    monkeypatch.setattr(tax, "_request", fake)
    with pytest.raises(tax.TaxError) as e:
        tax.fetch_tax("A1XYZ")
    assert e.value.status == 502


def test_fetch_tax_missing_status(monkeypatch: pytest.MonkeyPatch) -> None:
    no_status = "<html><body><div id='tax-status-panel'>Taxed</div></body></html>"
    monkeypatch.setattr(tax, "_request", make_fake_request(found=no_status))
    with pytest.raises(tax.TaxError) as e:
        tax.fetch_tax("A1XYZ")
    assert e.value.status == 502


# ── routes ──────────────────────────────────────────────────────────────────────

def test_tax_status(auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VES_SCRAPE_ENABLED", raising=False)
    assert auth_client.get("/api/tax/status").json == {"configured": True}
    monkeypatch.setenv("VES_SCRAPE_ENABLED", "0")
    assert auth_client.get("/api/tax/status").json == {"configured": False}


def test_get_tax_requires_auth(client: FlaskClient) -> None:
    assert client.get("/api/vehicles/1/tax").status_code == 401


def test_get_tax_vehicle_404(auth_client: FlaskClient) -> None:
    assert auth_client.get("/api/vehicles/999/tax").status_code == 404


def test_get_tax_empty(auth_client: FlaskClient, tax_enabled: None) -> None:
    v = mk_vehicle(auth_client, registration="A1 XYZ")
    r = auth_client.get(f"/api/vehicles/{v['id']}/tax")
    assert r.status_code == 200
    assert r.json == {"configured": True, "tax": None}


def test_refresh_tax_vehicle_404(auth_client: FlaskClient) -> None:
    assert auth_client.post("/api/vehicles/999/tax/refresh").status_code == 404


def test_refresh_tax_readonly_403(readonly_client: FlaskClient, garage: dict[str, Any]) -> None:
    from torqued.db import get_db
    from torqued.repositories.vehicle_repository import VehicleRepository

    with get_db() as db:
        v = VehicleRepository(db).create(garage["id"], {"name": "Shared bike"})
    assert readonly_client.post(f"/api/vehicles/{v['id']}/tax/refresh").status_code == 403


def test_refresh_tax_without_registration(auth_client: FlaskClient) -> None:
    v = mk_vehicle(auth_client)
    r = auth_client.post(f"/api/vehicles/{v['id']}/tax/refresh")
    assert r.status_code == 400
    assert "registration" in r.json["error"]


def test_refresh_tax_unconfigured(auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VES_SCRAPE_ENABLED", "0")
    v = mk_vehicle(auth_client, registration="A1 XYZ")
    assert auth_client.post(f"/api/vehicles/{v['id']}/tax/refresh").status_code == 503


def test_refresh_tax_relays_error(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tax_enabled: None
) -> None:
    def boom(reg: str) -> dict[str, Any]:
        raise tax.TaxError("No vehicle found for registration ZZ99ZZZ", 404)

    monkeypatch.setattr(tax, "fetch_tax", boom)
    v = mk_vehicle(auth_client, registration="ZZ99 ZZZ")
    r = auth_client.post(f"/api/vehicles/{v['id']}/tax/refresh")
    assert r.status_code == 404
    assert "No vehicle found" in r.json["error"]


def test_refresh_tax_stores_and_gets(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tax_enabled: None
) -> None:
    payload = {"registration": "A1XYZ", "tax_status": "Taxed",
               "tax_due_date": "2026-12-01", "make": "FORD", "colour": "Blue"}
    monkeypatch.setattr(tax, "fetch_tax", lambda reg: payload)
    v = mk_vehicle(auth_client, registration="A1 XYZ")

    r = auth_client.post(f"/api/vehicles/{v['id']}/tax/refresh")
    assert r.status_code == 200
    assert r.json["configured"] is True
    assert r.json["tax"]["tax_status"] == "Taxed"
    assert r.json["tax"]["tax_due_date"] == "2026-12-01"
    assert r.json["tax"]["raw"]["make"] == "FORD"

    g = auth_client.get(f"/api/vehicles/{v['id']}/tax")
    assert g.json["tax"]["registration"] == "A1XYZ"


def test_disconnect_clears_tax(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, tax_enabled: None
) -> None:
    payload = {"registration": "A1XYZ", "tax_status": "Taxed", "tax_due_date": "2026-12-01"}
    monkeypatch.setattr(tax, "fetch_tax", lambda reg: payload)
    v = mk_vehicle(auth_client, registration="A1 XYZ")
    auth_client.post(f"/api/vehicles/{v['id']}/tax/refresh")
    assert auth_client.get(f"/api/vehicles/{v['id']}/tax").json["tax"] is not None

    body = {"name": v["name"], "kind": v["kind"], "registration": "B2 YYY", "disconnect_mot": True}
    assert auth_client.put(f"/api/vehicles/{v['id']}", json=body).status_code == 200
    assert auth_client.get(f"/api/vehicles/{v['id']}/tax").json["tax"] is None


# ── tax reminders ───────────────────────────────────────────────────────────────

def _store_tax(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> dict[str, Any]:
    monkeypatch.delenv("VES_SCRAPE_ENABLED", raising=False)
    monkeypatch.setattr(tax, "fetch_tax", lambda reg: payload)
    v = mk_vehicle(auth_client, registration=payload["registration"])
    r = auth_client.post(f"/api/vehicles/{v['id']}/tax/refresh")
    assert r.status_code == 200, r.json
    return v


def _tax_reminders(auth_client: FlaskClient) -> list[dict[str, Any]]:
    return [r for r in auth_client.get("/api/reminders").json if r["type"] == "tax"]


def test_tax_reminder_due_soon(auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    due = (date.today() + timedelta(days=20)).isoformat()
    v = _store_tax(auth_client, monkeypatch,
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
    _store_tax(auth_client, monkeypatch,
               {"registration": "A1XYZ", "tax_status": "Untaxed", "tax_due_date": due})
    [rem] = _tax_reminders(auth_client)
    assert rem["status"] == "overdue"


def test_tax_reminder_outside_window_hidden(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    due = (date.today() + timedelta(days=120)).isoformat()
    _store_tax(auth_client, monkeypatch,
               {"registration": "A1XYZ", "tax_status": "Taxed", "tax_due_date": due})
    assert _tax_reminders(auth_client) == []


def test_tax_reminder_sorn_hidden(auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _store_tax(auth_client, monkeypatch,
               {"registration": "A1XYZ", "tax_status": "SORN", "tax_due_date": None})
    assert _tax_reminders(auth_client) == []


def test_tax_reminder_excludes_archived(
    auth_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    due = (date.today() + timedelta(days=20)).isoformat()
    v = _store_tax(auth_client, monkeypatch,
                   {"registration": "A1XYZ", "tax_status": "Taxed", "tax_due_date": due})
    auth_client.put(f"/api/vehicles/{v['id']}", json={"name": v["name"], "archived": True})
    assert _tax_reminders(auth_client) == []


def test_tax_reminders_empty_garages() -> None:
    from torqued.db import get_db
    from torqued.repositories.tax_repository import TaxRepository

    with get_db() as db:
        assert TaxRepository(db).reminders([]) == []
