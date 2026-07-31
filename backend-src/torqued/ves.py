"""Client for the DVLA Vehicle Enquiry Service (VES): a full vehicle snapshot.

The official VES API is the canonical source, but it is closed to new sign-ups. Until we
can get an API key this scrapes the same data from the public gov.uk "Check if a vehicle
is taxed" service (https://vehicleenquiry.service.gov.uk/), which needs no credentials.

One lookup returns the whole VES record the result page shows: tax + MOT status *and*
the vehicle profile (make, colour, first-registration date, year, cylinder capacity, CO₂,
fuel, Euro status, RDE, export marker, type approval, wheelplan, revenue weight, last V5C
date). All of it is captured in one fetch and stored in a single `vehicle_ves` record.

The public service is a small Rails wizard. One lookup is four requests sharing a
cookie session:

    1. GET  /                     — session cookie + the form's `authenticity_token`
    2. POST /vehicle-enquiry/save — the registration; 302 → /ConfirmVehicle (or
                                     /VehicleNotFound for an unknown plate)
    3. POST /vehicle-enquiry/save — confirm the vehicle; 302 → /VehicleFound
    4. (the GET the redirect lands on) — the result page with the full snapshot

The CSRF token is per-page, so it is re-read before each POST. This is a deliberate
stop-gap: the HTML is unversioned and behind a WAF, so keep lookups to on-demand
single-plate refreshes. `fetch_ves` returns a flat dict whose keys map 1:1 to the real
VES API fields, so swapping in the API later changes only this module's internals.

Set VES_SCRAPE_ENABLED=0 to turn lookups off (is_configured() → False).

Where the gov.uk host is unreachable but a whitelisted host is (e.g. a free
PythonAnywhere account, whose egress whitelist allows *.workers.dev but not
vehicleenquiry.service.gov.uk), set VES_RELAY_URL to a relay (the Cloudflare Worker in
relay/ves-worker/) that runs this same scrape and returns the same JSON; fetch_ves then
proxies through it instead of hitting gov.uk directly. See docs/VES_API.md →
"Production relay".

This scrapes unversioned HTML and WILL break when the service changes. When it
does, see docs/VES_API.md → "Maintenance & troubleshooting" for the exact page
structures this depends on, a symptom→fix table, and a step-by-step debug recipe.
"""
import http.cookiejar
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from typing import Any

BASE_URL = "https://vehicleenquiry.service.gov.uk"
SAVE_PATH = "/vehicle-enquiry/save?locale=en"
TIMEOUT = 15
# The default urllib User-Agent is rejected by the service's WAF; look like a browser.
_UA = "Mozilla/5.0 (compatible; Torqued/1.0; +https://github.com/xljones/torqued)"
# Void HTML elements never carry an end tag, so they must not affect nesting depth.
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
         "param", "source", "track", "wbr"}
_MONTHS = {
    name: i
    for i, name in enumerate(
        ["january", "february", "march", "april", "may", "june", "july", "august",
         "september", "october", "november", "december"],
        start=1,
    )
}


class VesError(Exception):
    """A VES lookup failed; `status` is the HTTP status to relay."""

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


def is_configured() -> bool:
    """Whether VES lookups are enabled (opt out with VES_SCRAPE_ENABLED=0)."""
    return os.environ.get("VES_SCRAPE_ENABLED", "1").strip() != "0"


def _relay_url() -> str:
    """Base URL of the VES relay, or '' when unset.

    When set, fetch_ves proxies through the relay (a Cloudflare Worker that runs the same
    scrape and returns the same snapshot JSON) instead of reaching gov.uk directly — for
    hosts whose outbound whitelist blocks the enquiry service. See docs/VES_API.md.
    """
    return os.environ.get("VES_RELAY_URL", "").strip()


# The vehicle-profile rows on the result page: our snapshot key -> the row's element id.
# Each is a GOV.UK summary row keyed by id wrapping a <dt> label and the <dd> value, read
# with _field(..., value_tag="dd"). `vehicleStatus` (tax) and the two MOT panels are read
# separately below.
_PROFILE_FIELDS = {
    "make": "make",
    "colour": "colour",
    "date_of_first_registration": "date_of_first_registration",
    "year_of_manufacture": "year_of_manufacture",
    "cylinder_capacity": "engine_capacity",
    "co2_emissions": "co2_emissions",
    "fuel_type": "fuel_type",
    "euro_status": "euro_status",
    "real_driving_emissions": "real_driving_emissions",
    "export_marker": "marked_for_export",
    "type_approval": "type_approval",
    "wheelplan": "wheelPlan",
    "revenue_weight": "revenue_weight",
    "date_of_last_v5c": "date_of_last_v5c_issued",
}


def normalise_registration(registration: str) -> str:
    return registration.replace(" ", "").upper()


class _TokenParser(HTMLParser):
    """Pull the `authenticity_token` from the form that posts to the save endpoint.

    The page carries more than one input named `authenticity_token` (the search form
    and the cookie-consent form); only the one inside the vehicle-enquiry form works.
    """

    def __init__(self) -> None:
        super().__init__()
        self._in_form = False
        self.token: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "form":
            self._in_form = "/vehicle-enquiry/save" in (a.get("action") or "")
        elif tag == "input" and self._in_form and a.get("name") == "authenticity_token":
            self.token = a.get("value") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._in_form = False


class _FieldParser(HTMLParser):
    """Collect the visible text of the element with a given id.

    When ``value_tag`` is given, only text inside that descendant tag is kept. The
    gov.uk result page puts each field in a summary row keyed by id that holds *both*
    a ``<dt>`` label and the ``<dd>`` value (``<div id="make"><dt>Vehicle make</dt>
    <dd>VOLKSWAGEN</dd></div>``), so we take the ``<dd>`` and drop the label.
    """

    def __init__(self, target_id: str, value_tag: str | None = None) -> None:
        super().__init__()
        self._target = target_id
        self._value_tag = value_tag
        self._in_target = 0  # nesting depth inside the target element
        self._in_value = 0  # nesting depth inside a value_tag descendant
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._in_target:
            if (tag == self._value_tag or self._in_value) and tag not in _VOID:
                self._in_value += 1
            if tag not in _VOID:
                self._in_target += 1
        elif dict(attrs).get("id") == self._target:
            self._in_target = 1

    def handle_endtag(self, tag: str) -> None:
        if self._in_value and tag not in _VOID:
            self._in_value -= 1
        if self._in_target and tag not in _VOID:
            self._in_target -= 1

    def handle_data(self, data: str) -> None:
        if self._in_target and (self._value_tag is None or self._in_value):
            self._parts.append(data)

    @property
    def text(self) -> str:
        return " ".join("".join(self._parts).split())


def _extract_token(html: str) -> str:
    parser = _TokenParser()
    parser.feed(html)
    if not parser.token:
        raise VesError("Could not read the vehicle-enquiry form", 502)
    return parser.token


def _field(html: str, target_id: str, value_tag: str | None = None) -> str | None:
    parser = _FieldParser(target_id, value_tag)
    parser.feed(html)
    return parser.text or None


def _parse_due_date(text: str | None) -> str | None:
    """Turn a 'Tax due: 1 December 2026' style string into an ISO date, else None."""
    if not text:
        return None
    match = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text)
    if not match:
        return None
    day, month_name, year = match.groups()
    month = _MONTHS.get(month_name.lower())
    if not month:
        return None
    try:
        return datetime(int(year), month, int(day)).date().isoformat()
    except ValueError:
        return None


def _request(
    opener: urllib.request.OpenerDirector,
    url: str,
    fields: dict[str, str] | None = None,
) -> tuple[str, str]:
    """GET, or POST when `fields` is given, following redirects; return (html, final_url)."""
    data = urllib.parse.urlencode(fields).encode() if fields is not None else None
    req = urllib.request.Request(url, data=data, headers={"User-Agent": _UA})
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            return resp.read().decode("utf-8", "replace"), resp.geturl()
    except urllib.error.HTTPError as e:
        e.close()
        raise VesError(f"Vehicle enquiry service error: {e.code} {e.reason}", 502) from e
    except Exception as e:
        raise VesError(f"Could not reach the vehicle enquiry service: {e}", 502) from e


def _fetch_via_relay(reg: str) -> dict[str, Any]:
    """Fetch the VES snapshot through the relay; it returns the same dict fetch_ves builds."""
    url = _relay_url().rstrip("/") + "/ves/" + urllib.parse.quote(reg)
    headers = {"User-Agent": _UA}
    token = os.environ.get("VES_RELAY_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            result: dict[str, Any] = json.loads(resp.read().decode())
            return result
    except urllib.error.HTTPError as e:
        e.close()
        if e.code == 404:
            raise VesError(f"No vehicle found for registration {reg}", 404) from e
        raise VesError(f"VES relay error: {e.code} {e.reason}", 502) from e
    except Exception as e:
        raise VesError(f"Could not reach the VES relay: {e}", 502) from e


def fetch_ves(registration: str) -> dict[str, Any]:
    """Fetch the full DVLA VES snapshot for a registration in one lookup.

    Returns a flat dict:
      * `registration`
      * `tax_status` ('Taxed'/'SORN'/'Untaxed'/…) and `tax_due_date` (ISO or None)
      * `mot_status` (the panel's status sentence, or None) and `mot_expiry_date`
        (ISO or None)
      * the vehicle profile — `make`, `colour`, `date_of_first_registration`,
        `year_of_manufacture`, `cylinder_capacity`, `co2_emissions`, `fuel_type`,
        `euro_status`, `real_driving_emissions`, `export_marker`, `type_approval`,
        `wheelplan`, `revenue_weight`, `date_of_last_v5c` (verbatim strings, or None)

    Only an unreadable *tax* status is fatal (a valid result page always has one); every
    other field is best-effort and left None when the row is absent (a bike has no CO₂,
    a vehicle may have no MOT, etc.). Raises VesError(404) for an unknown plate and
    VesError(502) for any other failure.

    The keys map 1:1 to the real VES API, so an API swap changes only this function.

    When VES_RELAY_URL is set the lookup is proxied through the relay; otherwise it
    scrapes gov.uk directly.
    """
    reg = normalise_registration(registration)
    if _relay_url():
        return _fetch_via_relay(reg)
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )

    home_html, _ = _request(opener, BASE_URL + "/")
    confirm_html, confirm_url = _request(
        opener,
        BASE_URL + SAVE_PATH,
        {"authenticity_token": _extract_token(home_html),
         "wizard_vehicle_enquiry_capture_vrn[vrn]": reg},
    )
    if "VehicleNotFound" in confirm_url:
        raise VesError(f"No vehicle found for registration {reg}", 404)

    found_html, found_url = _request(
        opener,
        BASE_URL + SAVE_PATH,
        {"authenticity_token": _extract_token(confirm_html),
         "wizard_vehicle_enquiry_capture_confirm_vehicle[confirmed]": "Yes"},
    )
    if "VehicleFound" not in found_url:
        raise VesError("Unexpected response from the vehicle enquiry service", 502)

    status = _field(found_html, "vehicleStatus", value_tag="dd")
    if not status:
        raise VesError("Could not read the vehicle tax status", 502)
    snapshot: dict[str, Any] = {
        "registration": reg,
        "tax_status": status,
        "tax_due_date": _parse_due_date(_field(found_html, "tax-status-panel")),
        # MOT is on the same result page: `mot_hidden_details` holds the status sentence
        # ("Vehicle … has a valid MOT certificate") and `mot-status-panel` the "Expires:
        # <date>". Both absent for a vehicle with no MOT — left as None, never fatal.
        "mot_status": _field(found_html, "mot_hidden_details"),
        "mot_expiry_date": _parse_due_date(_field(found_html, "mot-status-panel")),
    }
    # The rest of the vehicle profile — verbatim summary-row values, best-effort.
    for key, element_id in _PROFILE_FIELDS.items():
        snapshot[key] = _field(found_html, element_id, value_tag="dd")
    return snapshot
