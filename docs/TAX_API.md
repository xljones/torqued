# Road tax / SORN — reference

How Torqued gets a vehicle's **road-tax status**, **SORN**, and **tax due date**, how it
stores them, and how they surface as reminders.

## Source: the gov.uk vehicle enquiry service (a stop-gap)

The canonical source is the DVLA **Vehicle Enquiry Service (VES) API**, but it is closed to
new sign-ups. Until we can get an API key, Torqued scrapes the same data from the public
[Check if a vehicle is taxed](https://vehicleenquiry.service.gov.uk/) service, which needs no
credentials. Client → [`torqued/tax.py`](../backend-src/torqued/tax.py).

This is a deliberate stop-gap. `tax.fetch_tax(registration)` is shaped like
`mot.fetch_vehicle` so that when VES sign-ups reopen we can swap the client internals for the
API without touching the repository, routes, or UI.

### Scrape flow

The service is a small Rails wizard; one lookup is four requests sharing a cookie session:

1. `GET /` — session cookie + the form's `authenticity_token` (⚠ the page has two inputs of
   that name — the search form and the cookie-consent form; only the search-form one works).
2. `POST /vehicle-enquiry/save` with the registration → `302` to `/ConfirmVehicle`
   (known plate) or `/VehicleNotFound` (unknown → `404`).
3. `POST /vehicle-enquiry/save` with `confirmed=Yes` (re-reading the fresh per-page token) →
   `302` to `/VehicleFound`.
4. The `/VehicleFound` page carries the result — `#vehicleStatus` (`Taxed` / `SORN` /
   `Untaxed` / …) and a `#tax-status-panel` whose text includes `Tax due: 1 December 2026`.

Because it is unversioned HTML behind a WAF, keep lookups to **on-demand single-plate
refreshes** (never bulk). A browser-like `User-Agent` is sent so the WAF doesn't reject it.

### Config

| Env | Meaning |
|---|---|
| `VES_SCRAPE_ENABLED` | `1` (default) enables lookups; `0` disables them (`is_configured()` → False, so the UI hides the refresh and `refresh` returns 503). |

## What Torqued stores

`tax.fetch_tax` returns a normalised dict — `registration`, `tax_status`,
`tax_due_date` (ISO string or `None`), and best-effort `make`/`colour`. It is persisted one
row per vehicle in **`vehicle_tax`** (migration `0004`), keeping the whole payload in
`raw_json`:

| Column | Notes |
|---|---|
| `vehicle_id` | PK, FK → `vehicles.id` `ON DELETE CASCADE` |
| `registration` | normalised (spaces stripped, upper-cased) |
| `tax_status` | `Taxed` / `SORN` / `Untaxed` / `Not Taxed for on Road Use` |
| `tax_due_date` | ISO date, or `NULL` for SORN / untaxed |
| `raw_json` | the **tax facet** of the VES payload (`registration`, `tax_status`, `tax_due_date`, `make`, `colour`) — the MOT facet is stored on `vehicle_mot_status`, so the two records aren't identical |
| `fetched_at` | when it was last refreshed |

Repository → [`TaxRepository`](../backend-src/torqued/repositories/tax_repository.py):
`get_for_vehicle`, `replace_for_vehicle` (replace-on-refresh), `clear_for_vehicle` (used when
the plate is disconnected), and `reminders`.

### …and the current MOT status (same page, separate record)

The `/VehicleFound` page also shows the vehicle's **current MOT status** (an `#mot-status-panel`
with an `Expires: <date>`, and a visually-hidden `#mot_hidden_details` status sentence). This is
distinct from the **DVSA MOT *history*** (`mot_tests`) — it's DVLA's single current-status view,
and it's fresher than the DVSA feed for e.g. SORN vehicles the history feed lags on. So one
`fetch_tax` call also returns `mot_status` + `mot_expiry_date`, and they're persisted as their
own record in **`vehicle_mot_status`** (migration `0007`, same detached-record shape as
`vehicle_tax`) via
[`MotStatusRepository`](../backend-src/torqued/repositories/mot_status_repository.py). No extra
request is made — it's parsed from the page already fetched.

Consumers: the MOT card ([`MotCard.jsx`](../frontend-src/components/MotCard.jsx)) shows the
**later** of the DVSA test expiry and this VES expiry, and
[`MotRepository.reminders`](../backend-src/torqued/repositories/mot_repository.py) folds the VES
expiry into the single `type='mot'` reminder so a fresh VES status suppresses a false "overdue"
from stale DVSA history. Both records also appear on the admin
[records page](../frontend-src/components/VehicleRecordsPage.jsx) (source `motstatus`, labelled
"DVLA MOT status").

## Endpoints

Routes → [`torqued/routes/tax.py`](../backend-src/torqued/routes/tax.py), gated exactly like MOT.

| Route | Method | Access |
|---|---|---|
| `/api/tax/status` | GET | any logged-in user — `{configured}` |
| `/api/vehicles/<id>/tax` | GET | read access to the vehicle (404 if none) — `{configured, tax}` |
| `/api/vehicles/<id>/mot-status` | GET | read access (404 if none) — `{configured, mot_status}` (the VES MOT record) |
| `/api/vehicles/<id>/tax/refresh` | POST | write access (403 readonly) — one VES fetch; replaces **both** the tax and MOT-status snapshots; returns `{tax, mot_status}` |

`refresh` returns `400` with no registration, `503` when disabled, and relays the client's
status (`404` unknown plate, `502` scrape failure).

### When it's fetched

Tax data is **stored**, not fetched on every view. A refresh happens only when:

- a vehicle is **created** with a registration (the form calls `refreshTax` after create),
- a vehicle is **edited to a new registration** (Save re-fetches MOT + tax for the new plate), or
- the user refreshes the **MOT & tax** card on the vehicle detail page.

## Reminders

`TaxRepository.reminders` emits a reminder (tagged `type='tax'`, `title='Road tax'`,
`category='Tax'`) when the stored `tax_due_date` is within `TAX_DUE_SOON_DAYS` (30) —
`due_soon` — or already past — `overdue`. SORN / untaxed records carry no due date and so
raise no reminder; the **MOT & tax** card shows that status directly. Tax reminders are merged
into `ServiceLogRepository.reminders` alongside service and MOT reminders, so they appear on
the dashboard, the vehicle detail page, and the PDF report.

---

# Maintenance & troubleshooting (for a future agent)

**This is a scraper of an unversioned HTML page.** It *will* break when the gov.uk service
changes its markup or flow, or if its WAF starts blocking us. This section is the runbook:
what the scraper depends on, how failures show up, and how to diagnose and fix them. All code
is in [`torqued/tax.py`](../backend-src/torqued/tax.py); the parsing is done with stdlib
`html.parser` + one regex — no external deps.

## How one lookup works (mechanically)

`fetch_tax(reg)` drives a 4-request Rails wizard through a single cookie-jar opener
(`urllib` + `http.cookiejar`), following 302s automatically. A browser-like `User-Agent`
(`_UA`) is sent on every request because the WAF rejects the default `Python-urllib/*` UA.

| # | Call | What we extract / check |
|---|---|---|
| 1 | `GET /` | `authenticity_token` from the form whose `action` contains `/vehicle-enquiry/save` (`_extract_token`) |
| 2 | `POST /vehicle-enquiry/save` with `wizard_vehicle_enquiry_capture_vrn[vrn]=<REG>` | lands on `/ConfirmVehicle` (known) or `/VehicleNotFound` (→ `TaxError(404)`) |
| 3 | `POST /vehicle-enquiry/save` with `wizard_vehicle_enquiry_capture_confirm_vehicle[confirmed]=Yes` (using a **freshly re-read** token from the confirm page) | lands on `/VehicleFound`; anything else → `TaxError(502)` |
| 4 | (the page the redirect landed on) | read the result fields (below) |

Two easy-to-miss invariants:
- **The CSRF token is per-page.** It must be re-extracted from the confirm page before step 3
  — reusing step 1's token silently bounces back to `/` and step 3 fails.
- **The home page has two `authenticity_token` inputs** (the search form and the
  cookie-consent form). `_TokenParser` only takes the one inside the `…/save` form. If it ever
  grabs the wrong one, step 2 silently fails.

## The exact result-page markup we depend on

Captured live (registration blanked as `<REG>`). If a symptom below appears, re-capture this
(see the debug recipe) and compare.

**Status + due date** live in a panel keyed `#tax-status-panel`. `_parse_due_date` reads the
panel's *whole* text and regexes out `DD Month YYYY`, so it's resilient to surrounding markup:

```html
<!-- Taxed -->
<div class="… govuk-panel--fixed-height" id="tax-status-panel">
  <h2 class="govuk-panel__title …"><span aria-hidden="true"> ✓ Taxed </span>
    <span class="govuk-visually-hidden"> Vehicle <REG> is Taxed </span></h2>
  <div class="govuk-panel__body …"> … Tax due: 1 June 2027 … </div>
</div>

<!-- SORN: same heading shape, but the body is EMPTY → no due date → tax_due_date = null -->
<div class="… " id="tax-status-panel">
  <h2 …><span aria-hidden="true"> ✓ SORN </span>
    <span class="govuk-visually-hidden"> Vehicle <REG> has a valid SORN </span></h2>
  <div class="govuk-panel__body …"></div>
</div>
```

**Status / make / colour** are GOV.UK summary rows. The `id` is on the **row `<div>`**, which
wraps both a `<dt>` label and the `<dd>` value — so `_field(..., value_tag="dd")` is used to
take the `<dd>` and drop the `<dt>` label (without `value_tag` you'd get `"Vehicle status
Taxed"`):

```html
<div class="govuk-summary-list__row" id="vehicleStatus"><dt>Vehicle status</dt><dd>Taxed</dd></div>
<div class="govuk-summary-list__row" id="make"><dt>Vehicle make</dt><dd>VOLKSWAGEN</dd></div>
<div class="govuk-summary-list__row" id="colour"><dt>Vehicle colour</dt><dd>WHITE</dd></div>
```

`tax_status` values seen / documented: `Taxed`, `SORN`, `Untaxed`, `Not Taxed for on Road Use`.

**Current MOT status** lives in its own `#mot-status-panel` on the same page. `mot_status`
comes from the visually-hidden `#mot_hidden_details` sentence; `mot_expiry_date` from the panel's
`Expires: DD Month YYYY` (same `_parse_due_date` as tax). Both are optional — a vehicle with no
MOT record has no panel, and `fetch_tax` leaves them `None` rather than failing:

```html
<div class="… govuk-panel--fixed-height" id="mot-status-panel">
  <h2 class="govuk-panel__title …"><span aria-hidden="true"> ✓ MOT </span>
    <span class="govuk-visually-hidden" id="mot_hidden_details"> Vehicle <REG> has a valid MOT certificate </span></h2>
  <div class="govuk-panel__body …"> … Expires: 29 July 2027 … </div>
</div>
```

## Failure modes → symptom → what changed / where to fix

| Symptom (error relayed to the UI) | Most likely cause | Fix in `tax.py` |
|---|---|---|
| `502 Could not read the vehicle-enquiry form` | home/confirm form markup changed | `_TokenParser` — is the `action` still `…/vehicle-enquiry/save`? is the input still `name="authenticity_token"`? |
| `404` for a plate you know exists | step-2 redirect target string changed | the `"VehicleNotFound" in confirm_url` check + the `vrn` field name |
| `502 Unexpected response from the vehicle enquiry service` | flow changed (extra wizard step, renamed confirm field, or the success URL isn't `/VehicleFound`) | the `confirmed` field name + the `"VehicleFound" in found_url` check |
| `502 Could not read the vehicle tax status` | result page restructured; `#vehicleStatus` row/`<dd>` changed | `_field(found_html, "vehicleStatus", value_tag="dd")` |
| values carry a label prefix (e.g. `"Vehicle make VOLKSWAGEN"`) | the `id` moved onto the `<dd>`, or the value tag isn't `<dd>` anymore | the `value_tag` args in `fetch_tax` / `_FieldParser` |
| `tax_due_date` always `null` for a taxed vehicle | date text moved out of `#tax-status-panel`, or the format isn't `DD Month YYYY` | `_parse_due_date` (regex + `_MONTHS`) and which element it reads |
| `mot_status` / `mot_expiry_date` always `null` (MOT tile falls back to DVSA-only) | MOT panel restructured / renamed | `_field(found_html, "mot_hidden_details")` and `_parse_due_date(_field(found_html, "mot-status-panel"))` — are those ids still present? (never fatal: MOT is best-effort) |
| everything `502`, or works locally but not in prod | WAF blocking (UA rejected, rate-limited, IP blocked) or the site is down | `_UA`; reduce request volume; confirm the page loads in a normal browser first |

Note `_request` maps **any** HTTP error or network exception to `TaxError(502)` — so a `502`
with a vague message usually means "a step failed"; use the recipe below to find *which* step.

## Debug recipe

Run the flow manually in the backend container and dump each step's final URL + the anchors
the parser keys on. Swap `<REG>` for any real UK registration (e.g. your own vehicle):

```bash
docker compose run --rm backend python - <<'PY'
from torqued import tax
import http.cookiejar, urllib.request
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
home, u1 = tax._request(op, tax.BASE_URL + "/")
print("token:", tax._extract_token(home))                 # step-1 markup OK?
conf, u2 = tax._request(op, tax.BASE_URL + tax.SAVE_PATH,
    {"authenticity_token": tax._extract_token(home),
     "wizard_vehicle_enquiry_capture_vrn[vrn]": "<REG>"})
print("after vrn ->", u2)                                  # /ConfirmVehicle or /VehicleNotFound?
found, u3 = tax._request(op, tax.BASE_URL + tax.SAVE_PATH,
    {"authenticity_token": tax._extract_token(conf),
     "wizard_vehicle_enquiry_capture_confirm_vehicle[confirmed]": "Yes"})
print("after confirm ->", u3)                              # /VehicleFound?
for anchor in ('id="tax-status-panel"', 'id="vehicleStatus"', 'id="make"'):
    i = found.find(anchor)
    print("\n===", anchor, "===\n", repr(found[i-20:i+240]) if i >= 0 else "NOT FOUND")
PY
```

Read top-down: the first `print` that shows wrong/`NOT FOUND` output is the step that broke,
and the table above maps it to the fix. After changing a selector, re-capture the real HTML
into the fixtures in [`tests/test_tax.py`](../backend-src/tests/test_tax.py) (`HOME_HTML`,
`CONFIRM_HTML`, `found_html`) so the unit tests reflect the new reality, then re-run
`make test-backend`.

## Re-verify after a fix

```bash
docker compose run --rm backend python -c \
  "from torqued import tax, json; print(json.dumps(tax.fetch_tax('<REG>'), indent=2))"
```

Expected shapes: a **taxed** vehicle returns a `tax_due_date`; a **SORN**/untaxed vehicle
returns `"tax_due_date": null`. Both were verified live during development (a Taxed car and a
SORN car).

> ⚠️ The unit tests use canned HTML — they pass even if the live markup has drifted. A green
> `make test-backend` proves the *parser logic* is intact, **not** that it still matches the
> live site. Always finish with the live re-verify above.

## When the VES API reopens (retire the scraper)

The DVLA VES API returns the same facts far more robustly. `fetch_tax` is deliberately the
only scrape-aware code — everything downstream (`TaxRepository`, routes, UI) consumes its
plain dict. To swap:

1. Replace the body of `fetch_tax` with a VES API call (`POST /vehicle-enquiry/v1/vehicles`,
   `x-api-key` header, `{registrationNumber}` body) that returns the **same keys**:
   `registration`, `tax_status`, `tax_due_date` (ISO or `None`), `mot_status`,
   `mot_expiry_date` (ISO or `None`), `make`, `colour`. VES fields map 1:1: `taxStatus`,
   `taxDueDate`, `motStatus`, `motExpiryDate`, `make`, `colour` — so the MOT-status record
   swaps over with the tax record, no downstream change.
2. Point `is_configured()` at the API key env var instead of `VES_SCRAPE_ENABLED`.
3. Delete the scraper helpers (`_TokenParser`, `_FieldParser`, `_request`, `_extract_token`,
   `_field`, `_parse_due_date`) and their tests; the repository/route/UI tests are unaffected.
