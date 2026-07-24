"""Client for a vehicle's road-tax / SORN status.

The official DVLA Vehicle Enquiry Service (VES) API is the canonical source, but it
is closed to new sign-ups. Until we can get an API key this scrapes the same data
from the public gov.uk "Check if a vehicle is taxed" service
(https://vehicleenquiry.service.gov.uk/), which needs no credentials.

The public service is a small Rails wizard. One lookup is four requests sharing a
cookie session:

    1. GET  /                     — session cookie + the form's `authenticity_token`
    2. POST /vehicle-enquiry/save — the registration; 302 → /ConfirmVehicle (or
                                     /VehicleNotFound for an unknown plate)
    3. POST /vehicle-enquiry/save — confirm the vehicle; 302 → /VehicleFound
    4. (the GET the redirect lands on) — the result page with tax status + due date

The CSRF token is per-page, so it is re-read before each POST. This is a deliberate
stop-gap: the HTML is unversioned and behind a WAF, so keep lookups to on-demand
single-plate refreshes. `fetch_tax` is shaped like `mot.fetch_vehicle` so swapping in
the real VES API later is a drop-in.

Set VES_SCRAPE_ENABLED=0 to turn lookups off (is_configured() → False).

This scrapes unversioned HTML and WILL break when the service changes. When it
does, see docs/TAX_API.md → "Maintenance & troubleshooting" for the exact page
structures this depends on, a symptom→fix table, and a step-by-step debug recipe.
"""
import http.cookiejar
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


class TaxError(Exception):
    """A tax lookup failed; `status` is the HTTP status to relay."""

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


def is_configured() -> bool:
    """Whether tax lookups are enabled (opt out with VES_SCRAPE_ENABLED=0)."""
    return os.environ.get("VES_SCRAPE_ENABLED", "1").strip() != "0"


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
        raise TaxError("Could not read the vehicle-enquiry form", 502)
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
        raise TaxError(f"Vehicle enquiry service error: {e.code} {e.reason}", 502) from e
    except Exception as e:
        raise TaxError(f"Could not reach the vehicle enquiry service: {e}", 502) from e


def fetch_tax(registration: str) -> dict[str, Any]:
    """Fetch tax status, SORN, and tax due date for a registration.

    Returns a dict with `registration`, `tax_status` ('Taxed'/'SORN'/'Untaxed'/…),
    `tax_due_date` (ISO string or None), and best-effort `make`/`colour`. Raises
    TaxError(404) for an unknown plate and TaxError(502) for any other failure.
    """
    reg = normalise_registration(registration)
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
        raise TaxError(f"No vehicle found for registration {reg}", 404)

    found_html, found_url = _request(
        opener,
        BASE_URL + SAVE_PATH,
        {"authenticity_token": _extract_token(confirm_html),
         "wizard_vehicle_enquiry_capture_confirm_vehicle[confirmed]": "Yes"},
    )
    if "VehicleFound" not in found_url:
        raise TaxError("Unexpected response from the vehicle enquiry service", 502)

    status = _field(found_html, "vehicleStatus", value_tag="dd")
    if not status:
        raise TaxError("Could not read the vehicle tax status", 502)
    return {
        "registration": reg,
        "tax_status": status,
        "tax_due_date": _parse_due_date(_field(found_html, "tax-status-panel")),
        "make": _field(found_html, "make", value_tag="dd"),
        "colour": _field(found_html, "colour", value_tag="dd"),
    }
