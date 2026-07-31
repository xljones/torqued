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


def _relay_url() -> str:
    """Base URL of the VES relay, or '' when unset.

    When set, fetch_ves proxies through the relay (a Cloudflare Worker that runs the same
    scrape and returns the same snapshot JSON) instead of reaching gov.uk directly — for
    hosts whose outbound whitelist blocks the enquiry service. See docs/VES_API.md.
    """
    return os.environ.get("VES_RELAY_URL", "").strip()


def effective_endpoint() -> dict[str, str]:
    """Where a VES lookup actually goes: the relay if configured, else gov.uk directly.

    Surfaced in the admin panel so it's clear which outbound URL each lookup hits.
    """
    relay = _relay_url()
    if relay:
        return {"mode": "relay", "url": relay}
    return {"mode": "direct", "url": BASE_URL}


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


# ── Vehicle-detail baseline & DVSA/DVLA provenance ──────────────────────────────
#
# The DVSA MOT record and this DVLA VES snapshot describe the same vehicle, so many
# fields appear in both — but formatted differently ("1170" vs "1170 cc", an ISO date
# vs "October 2003", `Petrol` vs `PETROL`). `to_baseline` maps a stored VES snapshot
# onto the same detail-field keys DVSA uses (see mot.to_baseline), and `field_sources`
# reports, per field, which sources supplied it: DVSA, DVLA, or both when they agree
# once normalised. The vehicle-detail UI uses the first to display DVLA-only fields and
# the second to tag every field DVSA / DVLA / both.

# DVLA-only detail fields the VES page carries but DVSA does not. These key straight off
# the stored snapshot (the keys `fetch_ves` writes, i.e. the left side of _PROFILE_FIELDS).
_VES_ONLY = (
    "co2_emissions",
    "euro_status",
    "real_driving_emissions",
    "export_marker",
    "type_approval",
    "wheelplan",
    "revenue_weight",
    "date_of_last_v5c",
)


def _clean(value: Any) -> str | None:
    """Trim a snapshot value, treating blanks and DVLA's "Not available" as absent."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "not available":
        return None
    return text


def _int(value: Any) -> int | None:
    """The first run of digits in a value as an int (year, etc.), or None."""
    match = re.search(r"\d+", str(value)) if value is not None else None
    return int(match.group()) if match else None


def _digits(value: Any) -> str | None:
    """All digits in a value ("1170 cc" -> "1170"), or None when there are none."""
    cleaned = _clean(value)
    if cleaned is None:
        return None
    return re.sub(r"\D", "", cleaned) or None


def _month_key(value: Any) -> str | None:
    """A 'YYYY-MM' key from an ISO date or a '[day] Month YYYY' string, else None.

    DVSA gives a full ISO registration date; DVLA gives only the month of first
    registration ("October 2003"), so the sources can only be compared at month
    granularity.
    """
    cleaned = _clean(value)
    if cleaned is None:
        return None
    iso = re.match(r"(\d{4})-(\d{2})", cleaned)
    if iso:
        return f"{iso.group(1)}-{iso.group(2)}"
    named = re.search(r"([A-Za-z]+)\s+(\d{4})", cleaned)
    if named:
        month = _MONTHS.get(named.group(1).lower())
        if month:
            return f"{int(named.group(2))}-{month:02d}"
    return None


def _casefold(value: Any) -> str | None:
    cleaned = _clean(value)
    return cleaned.lower() if cleaned else None


def _reg_key(value: Any) -> str | None:
    cleaned = _clean(value)
    return normalise_registration(cleaned) if cleaned else None


def _year_key(value: Any) -> str | None:
    number = _int(value)
    return str(number) if number is not None else None


# Detail fields present in both sources: detail key -> (VES snapshot key, comparison key).
# The comparison key folds away formatting differences so equal data compares equal.
_SHARED = {
    "make": ("make", _casefold),
    "colour": ("colour", _casefold),
    "fuel_type": ("fuel_type", _casefold),
    "year": ("year_of_manufacture", _year_key),
    "engine_size": ("cylinder_capacity", _digits),
    "registration": ("registration", _reg_key),
    "registration_date": ("date_of_first_registration", _month_key),
}

# Every overridable DVSA detail field, so provenance covers DVSA-only ones (model, first
# used) too — they simply never gain a DVLA source.
_DVSA_FIELDS = (
    "make", "model", "year", "registration", "colour",
    "fuel_type", "engine_size", "first_used_date", "registration_date",
)


def to_baseline(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Map a stored VES snapshot onto vehicle-detail fields (DVLA display values).

    Shared fields are keyed the same as DVSA's baseline (see mot.to_baseline) so the UI
    can fall back to a DVLA value when DVSA lacks one; DVLA-only fields (CO₂, Euro status,
    …) are included verbatim. Absent / "Not available" values are dropped.
    """
    s = snapshot or {}
    out: dict[str, Any] = {
        "make": _clean(s.get("make")),
        "colour": _clean(s.get("colour")),
        "fuel_type": _clean(s.get("fuel_type")),
        "year": _int(s.get("year_of_manufacture")),
        "engine_size": _digits(s.get("cylinder_capacity")),
        "registration": _clean(s.get("registration")),
        "registration_date": _clean(s.get("date_of_first_registration")),
        **{key: _clean(s.get(key)) for key in _VES_ONLY},
    }
    return {k: v for k, v in out.items() if v is not None}


def field_sources(
    dvsa_baseline: dict[str, Any] | None, ves_snapshot: dict[str, Any] | None
) -> dict[str, list[str]]:
    """Per detail field, which sources supply it: ``["dvsa"]`` / ``["dvla"]`` / both.

    Both are listed only when the values agree once normalised (case, units, date
    granularity). When they disagree the DVSA value is the one displayed, so only DVSA is
    tagged. DVLA-only fields are tagged ``["dvla"]``.
    """
    dvsa = dvsa_baseline or {}
    ves = ves_snapshot or {}
    out: dict[str, list[str]] = {}
    for key in _DVSA_FIELDS:
        raw = dvsa.get(key)
        has_dvsa = raw is not None and str(raw) != ""
        sources = ["dvsa"] if has_dvsa else []
        shared = _SHARED.get(key)
        if shared:
            ves_key, to_key = shared
            ves_norm = to_key(ves.get(ves_key))
            if ves_norm is not None:
                if has_dvsa and to_key(raw) == ves_norm:
                    sources.append("dvla")
                elif not has_dvsa:
                    sources = ["dvla"]
        if sources:
            out[key] = sources
    for key in _VES_ONLY:
        if _clean(ves.get(key)) is not None:
            out[key] = ["dvla"]
    return out


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
