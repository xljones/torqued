# DVSA MOT History API — reference

What the official [DVSA MOT History API](https://documentation.history.mot.api.gov.uk/) returns, how
Torqued stores it, and the **baseline-with-overrides** model for the vehicle details panel.

> **Note — two MOT sources.** This is the DVSA MOT *history* (full test records). Torqued also
> reads DVLA's **current MOT status** (status + expiry) from the VES page it scrapes for road tax
> — see [VES_API.md](VES_API.md). The DVSA history feed lags for some vehicles (e.g. SORN), so the
> MOT card and the MOT reminder use the **later** of the DVSA test expiry and the VES expiry.

Field names below are quoted exactly as the API returns them (camelCase). The schema is taken from
DVSA's own published data models; Torqued additionally keeps the **entire raw response verbatim** in
`raw_json` (per vehicle and per test), so any field not yet surfaced is still captured.

---

## Endpoint & auth

```
GET https://history.mot.api.gov.uk/v1/trade/vehicles/registration/{registration}
```

- OAuth2 **client credentials** against Microsoft Entra ID (`grant_type=client_credentials`,
  `scope=https://tapi.dvsa.gov.uk/.default`), token cached ~60 min.
- Every request carries two headers: `Authorization: Bearer <token>` and `X-API-Key: <api-key>`.
- Config (env): `MOT_CLIENT_ID`, `MOT_CLIENT_SECRET`, `MOT_TOKEN_URL`, `MOT_API_KEY`.
- `404` → no record for that registration. Client → [`torqued/mot.py`](../backend-src/torqued/mot.py).

---

## Response shapes

The endpoint returns **one of two** vehicle objects depending on whether the vehicle has ever been
MOT tested.

### A. `VehicleWithMotResponse` — vehicle with ≥1 MOT/annual test

| Field | Type | Notes |
|---|---|---|
| `registration` | string \| null | Registration mark |
| `make` | string \| null | Manufacturer, e.g. `VOLKSWAGEN` |
| `model` | string \| null | Model, e.g. `PASSAT` |
| `firstUsedDate` | date \| null | First used in the UK |
| `fuelType` | string \| null | e.g. `Diesel`, `Petrol`, `Electric` |
| `primaryColour` | string \| null | e.g. `Blue` |
| `registrationDate` | date \| null | First registered in the UK |
| `manufactureDate` | date \| null | Date of manufacture |
| `engineSize` | string \| null | Cylinder capacity in **cc** (string) |
| `hasOutstandingRecall` | enum | `Yes` / `No` / `Unknown` / `Unavailable` |
| `motTests` | array | See [MOT test](#mot-test-object), newest first |

### B. `NewRegVehicleResponse` — newly registered, no MOT yet

| Field | Type | Notes |
|---|---|---|
| `registration` | string \| null | |
| `make` | string \| null | |
| `model` | string \| null | |
| `manufactureYear` | int \| null | Year of manufacture (this variant has no `manufactureDate`-derived test history) |
| `fuelType` | string \| null | |
| `primaryColour` | string \| null | |
| `registrationDate` | date \| null | |
| `manufactureDate` | date \| null | |
| `motTestDueDate` | date \| null | When the **first** MOT is due |
| `hasOutstandingRecall` | enum | `Yes` / `No` / `Unknown` / `Unavailable` |

> The two shapes differ: only variant A carries `firstUsedDate`, `engineSize`, and `motTests`; only
> variant B carries `manufactureYear` and `motTestDueDate`. Code must treat every field as optional.

### MOT test object

Three sub-types by `dataSource` — `DVSA` (Great Britain), `DVA NI` (Northern Ireland), `CVS`
(commercial). They share these fields:

| Field | Type | Notes |
|---|---|---|
| `completedDate` | datetime | When the test completed |
| `testResult` | enum | `PASSED` / `FAILED` (only passes & fails are returned) |
| `expiryDate` | date \| null | When the resulting certificate expires |
| `odometerValue` | int \| null | Reading at test time |
| `odometerUnit` | enum \| null | `MI` / `KM` |
| `odometerResultType` | enum | `READ` / `UNREADABLE` / `NO_ODOMETER` |
| `motTestNumber` | string \| null | 12-digit test number |
| `dataSource` | enum | `DVSA` / `DVA NI` / `CVS` |

Plus, depending on sub-type:

| Field | Present on | Type | Notes |
|---|---|---|---|
| `defects` | DVSA, CVS | array | Defects/advisories — see below (DVA NI returns none) |
| `location` | CVS | string \| null | ATF where the test was done |

### Defect object

| Field | Type | Notes |
|---|---|---|
| `text` | string \| null | Human-readable defect, e.g. `Nearside front tyre worn close to limit (5.2.3 (e))` |
| `type` | string \| null | Severity — commonly `DANGEROUS`, `MAJOR`, `MINOR`, `ADVISORY`, `FAIL` |
| `dangerous` | bool \| null | Whether flagged dangerous |

### Enums (exact values)

- **testResult:** `PASSED`, `FAILED`
- **odometerUnit:** `MI`, `KM`, `null`
- **odometerResultType:** `READ`, `UNREADABLE`, `NO_ODOMETER`
- **dataSource:** `DVSA`, `DVA NI`, `CVS`
- **hasOutstandingRecall:** `Yes`, `No`, `Unknown`, `Unavailable`

---

## How Torqued stores it

Written by [`MotRepository.replace_for_vehicle`](../backend-src/torqued/repositories/mot_repository.py)
(migration [`001_initial.sql`](../backend-src/torqued/migrations/001_initial.sql)):

- **`dvsa_vehicles`** — one row per vehicle: every scalar field above, snake_cased, plus `raw_json`
  (the full response) and `fetched_at`. `manufacture_year` and `mot_test_due_date` are populated only
  from variant B; the rest from variant A.
- **`mot_tests`** — one row per test: the test fields above, `defects_json`, and per-test `raw_json`.
- **Odometer sync** — `sync_odometer_logs` mirrors each test's reading into `odometer_logs` with
  `source='mot'` and `mot_test_number`, converted to canonical km. Replace-on-refresh (idempotent);
  manual logs untouched. These show on the mileage chart as amber points.

`unit` values are normalised `MI`/`KM` → `mi`/`km` to match the rest of the app.

---

## MOT as the baseline for vehicle details

The vehicle details panel shows DVSA data by default, but the user can override any value. DVSA stays
the live baseline (re-pulled on refresh); a user override always wins until cleared. Implemented in
migration [`003_vehicle_mot_overrides.sql`](../backend-src/torqued/migrations/003_vehicle_mot_overrides.sql),
`VehicleRepository.mot_baseline`, and the [`MotField`](../frontend-src/components/MotField.jsx) UI.

### Field mapping (MOT → vehicle detail)

| Vehicle detail field | MOT source | Notes |
|---|---|---|
| Registration | `registration` | |
| Make | `make` | |
| Model | `model` | |
| Colour | `primaryColour` | |
| Fuel | `fuelType` | |
| Year | `manufactureYear`, else year of `manufactureDate` / `firstUsedDate` | derive when only a date is present |
| Engine size (cc) | `engineSize` | `vehicles.engine_size` (migration 003) |
| First used | `firstUsedDate` | `vehicles.first_used_date` (migration 003) |
| First registered | `registrationDate` | `vehicles.registration_date` (migration 003) |
| VIN | — | not in the MOT API; user-only field |
| Tyre sizes/pressures, notes, name, kind | — | Torqued-only; never sourced from MOT |

### Resolution rule

For each mapped field the **effective value** is:

```
effective = vehicle_override (if set) else mot_snapshot_value
```

i.e. the `vehicles` columns become *overrides*. Leave one blank → it falls back to the MOT snapshot;
type a value → that wins. Clearing an override reverts to the MOT baseline. This means a user can add a
vehicle with just a registration + garage, hit **Refresh from DVSA**, and watch make/model/colour/fuel/
year populate automatically — while still being free to correct anything DVSA has wrong.

### How it works

1. **Schema** — migration `003` added `engine_size`, `first_used_date`, `registration_date` to
   `vehicles` (and `vehicle_history`). make/model/colour/fuel/year/registration already existed; all of
   these now act as nullable *overrides*.
2. **Resolver** — `GET /api/vehicles/<id>` returns the raw `vehicles` columns **plus** a `mot_baseline`
   object (mapped MOT values, with `year` derived from the best available date). The frontend resolves
   `effective = override ?? baseline` and infers provenance from whether the override is set — keeping
   the field mapping in one place (`VehicleRepository.mot_baseline`).
3. **UI** — [`MotField`](../frontend-src/components/MotField.jsx) renders the effective value, badges
   baseline values `MOT`, and offers **reset to MOT** on overrides that differ from the baseline (it
   resends the full vehicle with that one column nulled, since the update endpoint replaces all fields).
   The edit form ([`VehicleForm`](../frontend-src/components/VehicleForm.jsx)) shows the MOT value as the
   input placeholder (`MOT: …`), so leaving a field blank visibly means "use the DVSA value".
4. **Refresh** — replacing the snapshot updates the baseline without touching overrides, since overrides
   live in `vehicles` and the baseline lives in `dvsa_vehicles`.

Baseline resolution is applied on **both** the vehicle detail and the vehicle **list** endpoints
(`list_for_garages` batches the lookup), so a vehicle relying entirely on the MOT baseline shows its
make/model/year/plate on its card and its detail page alike, and the list filter matches baseline values.

### Torqued endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/mot/status` | `{configured}` — whether DVSA credentials are set (drives the form's Fetch button) |
| `GET /api/mot/lookup/<registration>` | Preview a plate's baseline **without storing** — prefills the create form |
| `POST /api/vehicles/<id>/mot/refresh` | Fetch **and store** the full record for a vehicle (the only write path) |
| `GET /api/vehicles/<id>/mot` | The stored snapshot + tests for the MOT history card |

The create/edit form leads with the registration (styled as a yellow plate); **Fetch from DVSA** previews
in create mode and refreshes-in-place in edit mode. On create, a previewed baseline is persisted via one
`refresh` so the new vehicle's detail/list show it immediately. Nothing else triggers a DVSA call —
suitable for a future daily background refresh that simply reuses the `refresh` store path.
