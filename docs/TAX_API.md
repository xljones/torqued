# DVLA Vehicle Enquiry Service (VES) API — reference

What the official [DVLA Vehicle Enquiry Service API](https://developer-portal.driver-vehicle-licensing.api.gov.uk/apis/vehicle-enquiry-service/vehicle-enquiry-service-description.html)
returns, how Torqued stores it, and how the road-tax due date becomes a reminder.

Torqued uses this purely for **road tax** (status + due date). MOT identity/history still
comes from the richer DVSA MOT History API — see [MOT_API.md](MOT_API.md).

---

## Endpoint & auth

```
POST https://driver-vehicle-licensing.api.gov.uk/vehicle-enquiry/v1/vehicles
Headers: x-api-key: <api-key>, Content-Type: application/json
Body:    {"registrationNumber": "<reg>"}
```

- A single **API key** in the `x-api-key` header — no OAuth (simpler than the DVSA MOT client).
- Config (env): `VES_API_KEY`, plus optional `VES_API_URL` to point at DVLA's UAT sandbox
  (`https://uat.driver-vehicle-licensing.api.gov.uk/vehicle-enquiry/v1/vehicles`).
- `404` → no record for that registration; `400` → DVLA couldn't read the registration.
  Both are relayed to the caller. Client → [`torqued/ves.py`](../backend-src/torqued/ves.py).

---

## Response shape

The endpoint returns a single vehicle object. Torqued stores **every** scalar field below as a
column (snake_cased) and keeps the verbatim payload in `raw_json` besides, so nothing is lost.
Only **Tax status** and **Tax due** are surfaced in the UI (DVSA is the identity baseline); the
rest are stored for querying/export.

| Field (API) | Column | Type | Notes |
|---|---|---|---|
| `registrationNumber` | `registration` | string | Registration mark |
| `taxStatus` | `tax_status` | enum | `Taxed` / `Untaxed` / `SORN` / `Not Taxed for on Road Use` |
| `taxDueDate` | `tax_due_date` | date \| null | When road tax is next due (null for SORN/untaxed) |
| `artEndDate` | `art_end_date` | date \| null | Additional-rate-of-tax end date |
| `motStatus` | `mot_status` | enum | `Valid` / `Not valid` / `No details held by DVLA` |
| `motExpiryDate` | `mot_expiry_date` | date \| null | DVLA's view of MOT expiry |
| `make` | `make` | string | |
| `colour` | `colour` | string | |
| `fuelType` | `fuel_type` | string | |
| `yearOfManufacture` | `year_of_manufacture` | int | |
| `engineCapacity` | `engine_capacity` | int | cc |
| `co2Emissions` | `co2_emissions` | int | g/km |
| `markedForExport` | `marked_for_export` | bool→0/1 | |
| `typeApproval` | `type_approval` | string | e.g. `M1` |
| `wheelplan` | `wheelplan` | string | |
| `revenueWeight` | `revenue_weight` | int | kg |
| `realDrivingEmissions` | `real_driving_emissions` | string | |
| `euroStatus` | `euro_status` | string | e.g. `EURO 6` |
| `dateOfLastV5CIssued` | `date_of_last_v5c_issued` | date | |
| `monthOfFirstRegistration` | `month_of_first_registration` | `YYYY-MM` | |
| `monthOfFirstDvlaRegistration` | `month_of_first_dvla_registration` | `YYYY-MM` | |
| `automatedVehicle` | `automated_vehicle` | bool→0/1 | |

---

## How Torqued stores it

Written by [`VesRepository.replace_for_vehicle`](../backend-src/torqued/repositories/ves_repository.py)
(migrations [`003_dvla_tax.sql`](../backend-src/torqued/migrations/003_dvla_tax.sql) +
[`004_dvla_tax_fields.sql`](../backend-src/torqued/migrations/004_dvla_tax_fields.sql)):

- **`dvla_vehicles`** — one row per vehicle: every scalar field from the table above as its own
  column, plus `raw_json` (the full verbatim response) and `fetched_at`. Replace-on-refresh.
  Booleans are stored as SQLite `0`/`1`.

---

## Tax due date as a reminder

[`VesRepository.tax_reminders`](../backend-src/torqued/repositories/ves_repository.py) turns each
stored `tax_due_date` into a reminder shaped like the service-log reminders (same keys), so the
dashboard and vehicle pages render both through one path. Status reuses the maintenance
`DUE_SOON_DAYS` window (30 days; tax has no mileage component): `overdue` if past, `due_soon`
within 30 days, else `upcoming`. The reminder carries `source: "tax"`, which the dashboard uses
to deep-link to the vehicle rather than a service log. Merging happens in
[`collect_reminders`](../backend-src/torqued/routes/vehicles.py), used by `GET /api/reminders`,
the vehicle detail endpoint, and the PDF report.

---

## Torqued endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/tax/status` | `{configured}` — whether `VES_API_KEY` is set (drives the refresh button) |
| `POST /api/vehicles/<id>/tax/refresh` | Fetch **and store** the DVLA record for a vehicle (the only write path) |
| `GET /api/vehicles/<id>/tax` | The stored snapshot for the vehicle's tax tiles |

The vehicle detail page's MOT card shows **Tax status** and **Tax due** tiles alongside the MOT
summary; its one "Refresh from DVSA & DVLA" button refreshes both sources at once. Unconfigured →
503 on refresh; unknown registration → 404 relayed from DVLA.
