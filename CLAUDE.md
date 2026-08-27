# Torqued — Claude Context

> A multi-tenant web app for logging vehicle maintenance (motorcycles & cars), split by garage. *All torque, no friction.*

## Tech stack

| Layer | Tech |
|---|---|
| Backend | Python 3.14, Flask, SQLite via SQLAlchemy ORM (PostgreSQL optional; psycopg v3 driver) |
| Migrations | Alembic (`backend-src/migrations/`); portable across Postgres and SQLite |
| Frontend | React 18, Vite, React Router |
| Auth | Flask-Login + `werkzeug.security` password hashing |
| Lint / typecheck / test | ruff, mypy, pytest (backend); eslint, vitest (frontend) |
| Dev environment | Docker Compose (two services: `backend`, `frontend`) |
| Deployment | PythonAnywhere (Flask serves built React `dist/`) |

**Database is configurable, not hard-coded.** The backend uses **SQLite by default**
(development, tests, and production) and can talk to PostgreSQL instead, through one
SQLAlchemy engine chosen by `torqued.db.database_url()`: `DATABASE_URL` (a full SQLAlchemy
URL, e.g. `postgresql+psycopg://…`) wins, else `DB_PATH` resolves to a `sqlite:///` URL,
else an on-disk SQLite file under `data/`. Repositories never import a driver — they get a
`Session` from `get_db()` and use the ORM directly (`execute_sql` remains for the occasional
raw `?`-placeholder statement). Dates and timestamps are stored as TEXT (ISO strings) and
0/1 flags as INTEGER so values round-trip identically on both backends. A bare
hosted-provider URL (`postgres://`/`postgresql://`) is accepted verbatim — the psycopg v3
driver is pinned and `?sslmode=…` passes through to libpq — and server-side prepared
statements are disabled so the app is safe behind a transaction pooler (PgBouncer).
Migrations are just `alembic upgrade head` (`run_migrations()`), run on startup or as an
explicit `make migrate` / CI step (see [DEPLOYMENT.md](DEPLOYMENT.md)).

## Domain model

- **Garage** — the tenant. All vehicles belong to a garage; everything else (services, odometer logs, photos) cascades through the vehicle. Garage names are unique.
- **Membership & roles** — `garage_members` links users to garages with a role: `owner` (manage members, rename garage), `member` (full read-write), `readonly` (view only). `users.is_admin` marks a **site admin**: implicit owner of every garage, and the only role that can create/delete garages and manage user accounts.
- **Access control** — `torqued/access.py`: `garage_role()` / `vehicle_role()` resolve a user's effective role; every route checks scope (404 if no access — existence is hidden) and write permission (403 for readonly). There is no global read-only flag; the old `before_request` readonly middleware is gone (only account expiry remains there).
- **Vehicle** — car or motorcycle; has a `garage_id`, per-vehicle odometer display unit (`mi`/`km`), tyre sizes/pressures, free-form key/value **specs**, and an `archived` flag. Identity fields that the DVSA MOT record can supply (make, model, year, registration, colour, fuel, engine_size, first_used_date, registration_date) act as **nullable overrides**: the vehicle **detail and list** endpoints return the raw columns plus a `mot_baseline` object (mapped by `mot.to_baseline`), and the UI shows `override ?? baseline` with a "reset to MOT" affordance. The vehicle form leads with the registration (yellow plate styled in the official UK "Charles Wright" typeface, `styles/fonts/CharlesWright-Bold.woff2`) and a **Fetch from DVSA** button: `GET /api/mot/lookup/<reg>` previews in create mode, `GET /api/mot/status` gates the button, refresh stores. In **edit** mode each identity field renders as a split control — a two-thirds editable override next to a one-third fixed DVSA baseline value, with a green border marking whichever one will be used. See [docs/MOT_API.md](docs/MOT_API.md).
- **ServiceLog** — one maintenance event (date, title, category, performed_by, cost, odometer, optional `next_due_date`/`next_due_km`). Can have zero or more **fault codes** (OBD-II DTCs) recorded in `service_log_fault_codes` (migration `004`). The form uses autocomplete from the existing `dtc.py` lookup but accepts free-text codes too. The detail view expands each code's description and system if found in the OBD-II database.
- **OdometerLog** — a mileage reading with a `source` ('manual' user entry, or 'mot' mirrored from a DVSA test by `mot_test_number`). Mileage timelines and "latest odometer" merge these with service-log readings; `mileage_series` tags each point with its source ('manual'/'service'/'mot') for the chart.
- **Photo** — upload attached to a vehicle, optionally scoped to a service log. Files live in `data/uploads/` (env `UPLOAD_DIR`), records in the `photos` table.
- **Reminders** are derived, not stored: any service log with a `next_due_*` value creates one until a newer log in the same category exists. Status is `overdue` / `due_soon` / `upcoming`. Reminders are tagged `type` (`service`); a vehicle's **MOT** also surfaces here (`type='mot'`, no `upcoming`): `MotRepository.reminders` emits an `overdue` (lapsed) or `due_soon` reminder once the MOT expiry — the latest test's `expiry_date`, falling back to the DVSA `mot_test_due_date` — falls inside the MOT window. Road **tax** works the same way (`type='tax'`): `VesRepository.reminders` emits `overdue`/`due_soon` from the stored `tax_due_date`, while SORN/untaxed vehicles carry no due date and so raise no reminder. `ServiceLogRepository.reminders` merges the service, schedule, MOT and tax streams so all appear wherever reminders do (dashboard, vehicle detail, PDF report).
- **Reminder windows** — how far ahead something counts as `due_soon` is **per garage**, not global. `torqued/reminders.py` owns the defaults (service **90 days / 2,000 mi**, MOT 60 days, tax 30 days) and the frozen `ReminderWindows` value object; `garages.reminder_{service_days,service_km,service_unit,mot_days,tax_days}` (migration `0009`, nullable — NULL means "use the default") hold a garage's overrides, edited by an owner through `PUT /api/garages/<id>/settings` and the Settings page. Because one `GET /api/reminders` can span every garage a user belongs to, `GarageRepository.reminder_windows(garage_ids)` resolves a `{garage_id: ReminderWindows}` map once per run and `ServiceLogRepository.reminders` threads it into the MOT / VES / schedule streams (the same trick as the `latest_odometers` map); each accepts it as an optional `windows=` kwarg and resolves its own when called standalone.
- **Fault codes (DTCs)** — `torqued/dtc.py` serves OBD-II code lookups from the vendored `data/obd_codes.json` (2,100+ generic SAE J2012 powertrain codes, MIT-licensed from github.com/fabiovila/OBDIICodes). Codes outside the dataset still get a structural decode (system / generic-vs-manufacturer scope / P-code subsystem). Routes: `GET /api/codes/<code>`, `GET /api/codes?q=` (an empty/blank `q` returns the full list — `dtc.list_all` — so the lookup page shows every code before searching; non-empty searches stay capped at 25).
- **MOT history (UK)** — `torqued/mot.py` is a client for the official DVSA MOT History API (OAuth2 client-credentials via Microsoft Entra + `X-API-Key`; env vars `MOT_CLIENT_ID`, `MOT_CLIENT_SECRET`, `MOT_TOKEN_URL`, `MOT_API_KEY`; token cached ~60 min). `POST /api/vehicles/<id>/mot/refresh` (write roles) fetches by the vehicle's registration and stores **everything**: a per-vehicle snapshot in `dvsa_vehicles` and each test in `mot_tests` (both keep the verbatim API payload in `raw_json`), then mirrors test odometer readings into `odometer_logs` with `source='mot'` (replace-on-refresh; manual logs untouched) so they appear in the mileage timeline. `GET /api/vehicles/<id>/mot` returns `{configured, mot}`; `GET /api/mot/status` and `GET /api/mot/lookup/<reg>` (preview, no persist) support the form. Unconfigured → 503 on refresh/lookup; unknown registration → 404 relayed from DVSA. Full response schema + the MOT-baseline/user-override model for vehicle details: [docs/MOT_API.md](docs/MOT_API.md).
- **DVLA Vehicle Enquiry Service (VES, UK)** — `torqued/ves.py` resolves a vehicle's **full VES snapshot** in one lookup: tax status / SORN / tax due date, current **MOT status + expiry**, and the vehicle profile (make, colour, first-registration date, year, cylinder capacity, CO₂, fuel, Euro status, RDE, export marker, type approval, wheelplan, revenue weight, last V5C date). The official VES API is closed to sign-ups, so this **scrapes** the public gov.uk "Check if a vehicle is taxed" service (`vehicleenquiry.service.gov.uk`) — no credentials, always available — behind a `fetch_ves(reg)` dict whose flat keys map 1:1 to the VES API, so it's a drop-in swap when sign-ups reopen. It is **distinct from the DVSA MOT *history*** (`mot_tests`); the MOT card and reminder use the **later** of the DVSA test expiry and the VES expiry, so a fresh VES status corrects a stale DVSA history (e.g. SORN vehicles). One lookup is stored as **one record** in `vehicle_ves` with the same **retain-as-history** shape as `dvsa_vehicles` (surrogate `id` + nullable `vehicle_id` / `ON DELETE SET NULL`, migration `0007` renames + extends the old `vehicle_tax`): each refresh keeps the prior lookup detached, records survive vehicle deletion, and `VesRepository.relink_detached` re-ties a plate's records to a vehicle added later — mirroring `MotRepository`. `POST /api/vehicles/<id>/ves/refresh` (write roles) fetches + stores; `GET /api/vehicles/<id>/ves` reads the live snapshot; `GET /api/ves/status` gates the UI. VES is folded into the vehicle-detail **MOT & tax** card and fetched only on vehicle create or an explicit refresh (never per-view). On the vehicle-detail **info card**, DVSA and DVLA are **consolidated per field**: `ves.to_baseline`/`ves.field_sources` normalise the shared fields (e.g. engine `"1170"` vs `"1170 cc"`, ISO date vs `"October 2003"`, case-folded make/colour/fuel) so `GET /api/vehicles/<id>` returns `ves_baseline` + `field_sources` next to the DVSA `mot_baseline`, and [`MotField`](frontend-src/components/MotField.jsx) tags each field **DVSA**, **DVLA**, or **both** (when they agree); DVLA-only fields (CO₂, Euro status, RDE, export marker, type approval, wheelplan, revenue weight, last V5C) render as extra rows tagged DVLA. Where the host's outbound whitelist blocks gov.uk (free PythonAnywhere blocks `vehicleenquiry.service.gov.uk` but allows `*.workers.dev`), set `VES_RELAY_URL` and `fetch_ves` proxies the scrape through the Cloudflare Worker in `relay/ves-worker/` (covers both `/ves/refresh` and the admin records lookup). See [docs/VES_API.md](docs/VES_API.md).

**Units:** distances are stored canonically in **km** (`odometer_km`, `next_due_km`) along with the unit the user typed; tyre pressures are stored in **psi**. Conversion helpers: `torqued/units.py` (backend), `frontend-src/units.js` (frontend, incl. psi↔bar).

## Architecture

### Backend (`backend-src/`)

DDD-inspired layering — routes never write SQL directly.

```
backend-src/
  alembic.ini        Alembic config (URL resolved from the app config, not hard-coded)
  migrations/        Alembic environment + versions/ (outside the torqued package, so
                     it stays out of the test-coverage scope)
torqued/
  __init__.py        create_app() factory; Flask-Login setup, before_request auth guard
  db.py              DB-agnostic SQLAlchemy layer: database_url() resolution, cached engine,
                     get_db() Connection wrapper, IntegrityError re-export, run_migrations()
                     (= alembic upgrade head)
  units.py           mi/km conversion + request payload parsing
  access.py          Per-garage role resolution and write checks (owner/member/readonly)
  dtc.py             OBD-II fault code lookup + SAE J2012 structural decoding
  mot.py             DVSA MOT History API client (OAuth2 + X-API-Key, cached token)
  tax.py             Road-tax / SORN status (scrapes the gov.uk vehicle enquiry service)
  data/              obd_codes.json — vendored generic DTC descriptions
  domain/            Plain dataclasses: Garage, Vehicle, ServiceLog, OdometerLog, Photo, User
  repositories/      GarageRepository, VehicleRepository, ServiceLogRepository,
                     OdometerLogRepository, PhotoRepository, UserRepository,
                     MotRepository, TaxRepository — own all SQL
  routes/            Flask Blueprints: admin, auth, garages, vehicles, services, odometer,
                     mot, tax, photos, codes, export (services CSV/TSV/JSON, vehicle PDF report),
                     search, users
```

- **Adding a schema change:** create an Alembic revision — `alembic revision -m "…"` from `backend-src/`, or hand-write a file in `migrations/versions/`. It runs automatically on next startup (`run_migrations()` → `alembic upgrade head`) and is recorded in `alembic_version`. Keep migrations **portable**: use `sa` types (not raw Postgres DDL) so they also apply to the SQLite test database; the only dialect branch is the `CURRENT_TIMESTAMP` default. SQL itself stays driver-agnostic — qmark (`?`) placeholders, `RETURNING id` instead of `lastrowid`, `LOWER(x) = LOWER(?)` instead of `COLLATE NOCASE`.
- **Adding an endpoint:** add a method to the relevant repository, call it from the relevant blueprint.
- **Auth:** Flask-Login guards all routes via `@login_required`; a `before_request` hook in `__init__.py` enforces account expiry (logs the user out). Read-only is per-garage and enforced in routes via `torqued.access`.
- **Tenancy:** collection endpoints accept an optional `garage_id` query param and otherwise return data for all the user's garages; item endpoints resolve the garage through the vehicle. Out-of-scope resources return 404, write attempts by readonly members return 403.
- **Version history:** vehicles and service logs snapshot to `*_history` tables on every create/update; `revert` endpoints restore a snapshot.
- **Admin-only:** `routes/admin.py` exposes `/api/admin/pythonanywhere` (CPU, web app, scheduled task info — needs `PA_API_TOKEN` and `PA_USERNAME`), gated on `current_user.is_admin`.

### Frontend (`frontend-src/`)

```
App.jsx              Shell: checks auth state, renders LoginPage or the main layout (sidebar + bottom nav)
AuthContext.jsx      Provides user (incl. memberships), garages, currentGarage +
                     selectGarage (persisted to localStorage), roleFor(garageId)
ThemeContext.jsx     Light/dark/system theme: mode persisted to localStorage (torqued.theme),
                     resolved + applied as <html data-theme>; System tracks prefers-color-scheme live
DisplayPrefsContext.jsx  Client-side display prefs (localStorage). titleCaseNames (default on,
                     torqued.titleCaseNames) exposes formatName(), which title-cases DVSA-sourced
                     make/model/colour/fuel for display only — never user overrides; useDisplayPrefs()
                     is null-safe (passthrough without a provider)
api.js               Thin fetch wrapper (JSON + multipart upload); all calls use credentials: 'include'
units.js             mi/km + psi/bar conversion and formatting
constants.js         FormMode, vehicle kinds, service categories, reminder labels
styles/              Per-concern CSS modules (base, buttons, cards, forms, layout, garage, …)
components/          Pages: Dashboard, VehicleList, VehicleDetail, VehicleForm,
                     ServiceList, ServiceDetail, ServiceForm, CodeLookup, LoginPage,
                     SettingsPage, AdminPage (site admin: garages + users +
                     memberships + PythonAnywhere stats), VehicleRecordsPage
                     (site admin: unified DVLA tax + DVSA records, /records)
                     Shared: PhotoGallery, DvsaRecord, MotCard, MotField, MileageChart, FaultCodeInput,
                     SuggestInput, ExportDropdown, PythonAnywhereStats, RelativeTime,
                     Skeleton, BuildInfo, Toast
```

- **PhotoGallery** — grid + lightbox + caption editing; uploads multipart to `/api/vehicles/<id>/photos` (optionally scoped to a service log).
- **VehicleDetail** — reminders, info card, tyre pressures (psi & bar), editable spec list, mileage card (interactive chart with per-point source tooltips, year-boundary markers, and a quick-add form that warns when a reading would go backwards relative to a dated neighbour), MOT history card (DVSA refresh, summary tiles, per-test defects), service history, photos, version history.
- **ServiceList** — garage-scoped service history, filterable by free text and by a specific vehicle.
- **Garage switcher** — in the sidebar (and mobile More menu); list pages (Dashboard, VehicleList, ServiceList) are scoped to `currentGarage`, detail pages derive the role from the resource's `garage_id` via `roleFor`.
- **SettingsPage** (`/settings`) — sectioned settings page (Account, Appearance, Password). The **Appearance** section switches the theme (Light / Dark / System) via `ThemeContext`; a one-tap theme cycle button also lives in the sidebar and mobile More menu. Dark mode is driven entirely by CSS custom properties: light values live in `styles/base.css :root`, dark overrides in `styles/dark.css` under `[data-theme="dark"]`. Appearance also holds a **Tidy up vehicle names** On/Off toggle (`DisplayPrefsContext`) that title-cases DVSA make/model/colour/fuel on display only — the stored ALL-CAPS record is unchanged and user-typed overrides are shown verbatim.
- **AdminPage** — site-admin page at `/admin`: create/rename/delete garages; create/delete users (optionally assigning a garage + role); manage an existing user's garage memberships and roles via the per-user editor (`addMember`/`setMemberRole`/`removeMember`); PythonAnywhere stats. This is now the only UI for membership management — the former per-garage Members page was removed. The owner-role member endpoints (`POST/PUT/DELETE /api/garages/<id>/members`) still exist server-side, reachable via this admin UI or `make add-member`.

## Running locally

```bash
make run            # start all services (Postgres + backend + frontend)
make stop           # stop
make logs           # tail logs (make logs service=backend for one service)
make build          # rebuild images (needed after requirements.txt or Dockerfile changes)
make build-frontend # compile React into dist/ (for local production preview)
```

`make run` brings up a `db` (Postgres 17) service; the backend connects to it via
`DATABASE_URL` (set in `compose.yml`). Postgres data persists in the `pgdata` volume.

### Database & users

```bash
make migrate                                       # apply pending migrations (local DB)
make migrate prod=1                                # ... against PROD_DATABASE_URL (manage.py migrate --prod)
make seed                                          # sample data (1 garage, 3 vehicles, 9 services)
make reset-db                                      # drop all tables (interactive confirm) — including users
make db-backup                                     # write data/db-backup-<timestamp>.sql
make db-restore file=db-backup-<timestamp>.sql     # restore from backup (interactive confirm)

make create-user  username=x password=y            # normal user (no garages yet)
make create-admin username=x password=y            # site admin
make create-garage name="Home Garage"              # new garage
make add-member garage="Home Garage" username=x role=member   # owner|member|readonly
make rename-user  username=x new_username=y
make delete-user  username=x                       # interactive confirm
make list-users
```

Append `prod=1` to any of these except `seed` to run against the production database
(`PROD_DATABASE_URL`) instead of the local one — e.g. `make create-admin username=x
password=y prod=1`. `manage.py` strips a global `--prod` and repoints `DATABASE_URL` once
(printing the target host); destructive commands still prompt. On PythonAnywhere
`DATABASE_URL` already is production, so `prod=1` isn't used (and errors) there.

### Dev tooling

```bash
make format            # ruff format the backend
make lint-backend      # ruff check + mypy
make lint-frontend     # eslint
make test-backend      # pytest with 100% coverage gate (see pyproject.toml)
make test-frontend     # vitest
make test              # all of the above (mirrors CI)
```

Locally the database is PostgreSQL in the `db` container (data in the `pgdata` volume); uploaded photos live in `data/uploads/` (bind-mounted into the backend container). Tests use a throwaway SQLite file per the `DB_PATH` the `conftest` fixture sets. `db-backup`/`db-restore` detect the backend automatically (`pg_dump`/`psql` for Postgres, `sqlite3` dump for SQLite).

## PythonAnywhere deployment

```bash
make deploy-pa    # reset to origin/deploy, install deps, back up + migrate the DB (behind a maintenance page), then reload
```

`deploy-pa` runs `manage.py db-backup --keep 3` then `manage.py migrate` (on PA
`DATABASE_URL` *is* production) wrapped in `touch MAINTENANCE` / `rm MAINTENANCE`. The
backup is a pre-migration rollback point taken with the site quiesced; `--keep 3` prunes
all but the 3 newest `data/db-backup-*.sql` files so each deploy leaves a short rolling
window. While that flag file exists, every request gets a 503 maintenance page (a
`before_request` hook in `__init__.py` checks `MAINTENANCE_FILE`, defaulting to a
`MAINTENANCE` file at the project root) — covering the brief backup + migration window. A
failed backup or migration leaves the flag in place on purpose. `manage.py` now loads the
project `.env` (via `python-dotenv`) so CLI commands target the same database as the web app.

All `make` commands listed under **Database & users** above auto-detect the environment: on PythonAnywhere they run via `venv/bin/python backend-src/manage.py` directly; locally they go through Docker. Detection uses `PYTHONANYWHERE_SITE`, an env var PythonAnywhere injects automatically into every console and web process (set to the site's domain, e.g. `username.pythonanywhere.com`).

See [DEPLOYMENT.md](DEPLOYMENT.md) for first-time setup.

## Key conventions

- Commit format: `feat/fix/chore(component): one-line description`
- Small, focused commits — never bulk everything together
- Never commit or push without explicit instruction
- Backend changes that don't touch `requirements.txt` or `Dockerfile.backend` hot-reload via the bind mount — no rebuild needed
- Frontend changes hot-reload via Vite — no rebuild needed
