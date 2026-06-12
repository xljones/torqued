# Torqued — Claude Context

> A multi-tenant web app for logging vehicle maintenance (motorcycles & cars), split by garage. *All torque, no friction.*

## Tech stack

| Layer | Tech |
|---|---|
| Backend | Python 3.14, Flask, SQLite (built-in `sqlite3`) |
| Frontend | React 18, Vite, React Router |
| Auth | Flask-Login + `werkzeug.security` password hashing |
| Lint / typecheck / test | ruff, mypy, pytest (backend); eslint, vitest (frontend) |
| Dev environment | Docker Compose (two services: `backend`, `frontend`) |
| Deployment | PythonAnywhere (Flask serves built React `dist/`) |

## Domain model

- **Garage** — the tenant. All vehicles belong to a garage; everything else (services, odometer logs, photos) cascades through the vehicle. Garage names are unique.
- **Membership & roles** — `garage_members` links users to garages with a role: `owner` (manage members, rename garage), `member` (full read-write), `readonly` (view only). `users.is_admin` marks a **site admin**: implicit owner of every garage, and the only role that can create/delete garages and manage user accounts.
- **Access control** — `torqued/access.py`: `garage_role()` / `vehicle_role()` resolve a user's effective role; every route checks scope (404 if no access — existence is hidden) and write permission (403 for readonly). There is no global read-only flag; the old `before_request` readonly middleware is gone (only account expiry remains there).
- **Vehicle** — car or motorcycle; has a `garage_id`, per-vehicle odometer display unit (`mi`/`km`), tyre sizes/pressures, free-form key/value **specs**, and an `archived` flag. Identity fields that the DVSA MOT record can supply (make, model, year, registration, colour, fuel, engine_size, first_used_date, registration_date) act as **nullable overrides**: the vehicle **detail and list** endpoints return the raw columns plus a `mot_baseline` object (mapped by `mot.to_baseline`), and the UI shows `override ?? baseline` with a "reset to MOT" affordance. The vehicle form leads with the registration (yellow plate styled in the official UK "Charles Wright" typeface, `styles/fonts/CharlesWright-Bold.woff2`) and a **Fetch from DVSA** button: `GET /api/mot/lookup/<reg>` previews in create mode, `GET /api/mot/status` gates the button, refresh stores. See [docs/MOT_API.md](docs/MOT_API.md).
- **ServiceLog** — one maintenance event (date, title, category, performed_by, cost, odometer, optional `next_due_date`/`next_due_km`). Can have zero or more **fault codes** (OBD-II DTCs) recorded in `service_log_fault_codes` (migration `004`). The form uses autocomplete from the existing `dtc.py` lookup but accepts free-text codes too. The detail view expands each code's description and system if found in the OBD-II database.
- **OdometerLog** — a mileage reading with a `source` ('manual' user entry, or 'mot' mirrored from a DVSA test by `mot_test_number`). Mileage timelines and "latest odometer" merge these with service-log readings; `mileage_series` tags each point with its source ('manual'/'service'/'mot') for the chart.
- **Photo** — upload attached to a vehicle, optionally scoped to a service log. Files live in `data/uploads/` (env `UPLOAD_DIR`), records in the `photos` table.
- **Reminders** are derived, not stored: any service log with a `next_due_*` value creates one until a newer log in the same category exists. Status is `overdue` / `due_soon` (≤30 days or ≤500 km away) / `upcoming`.
- **Fault codes (DTCs)** — `torqued/dtc.py` serves OBD-II code lookups from the vendored `data/obd_codes.json` (2,100+ generic SAE J2012 powertrain codes, MIT-licensed from github.com/fabiovila/OBDIICodes). Codes outside the dataset still get a structural decode (system / generic-vs-manufacturer scope / P-code subsystem). Routes: `GET /api/codes/<code>`, `GET /api/codes?q=`.
- **MOT history (UK)** — `torqued/mot.py` is a client for the official DVSA MOT History API (OAuth2 client-credentials via Microsoft Entra + `X-API-Key`; env vars `MOT_CLIENT_ID`, `MOT_CLIENT_SECRET`, `MOT_TOKEN_URL`, `MOT_API_KEY`; token cached ~60 min). `POST /api/vehicles/<id>/mot/refresh` (write roles) fetches by the vehicle's registration and stores **everything**: a per-vehicle snapshot in `dvsa_vehicles` and each test in `mot_tests` (both keep the verbatim API payload in `raw_json`), then mirrors test odometer readings into `odometer_logs` with `source='mot'` (replace-on-refresh; manual logs untouched) so they appear in the mileage timeline. `GET /api/vehicles/<id>/mot` returns `{configured, mot}`; `GET /api/mot/status` and `GET /api/mot/lookup/<reg>` (preview, no persist) support the form. Unconfigured → 503 on refresh/lookup; unknown registration → 404 relayed from DVSA. Full response schema + the planned MOT-baseline/user-override model for vehicle details: [docs/MOT_API.md](docs/MOT_API.md).

**Units:** distances are stored canonically in **km** (`odometer_km`, `next_due_km`) along with the unit the user typed; tyre pressures are stored in **psi**. Conversion helpers: `torqued/units.py` (backend), `frontend-src/units.js` (frontend, incl. psi↔bar).

## Architecture

### Backend (`backend-src/`)

DDD-inspired layering — routes never write SQL directly.

```
torqued/
  __init__.py        create_app() factory; Flask-Login setup, before_request auth guard
  db.py              get_db(), run_migrations() — migration runner reads migrations/*.sql
  units.py           mi/km conversion + request payload parsing
  access.py          Per-garage role resolution and write checks (owner/member/readonly)
  dtc.py             OBD-II fault code lookup + SAE J2012 structural decoding
  mot.py             DVSA MOT History API client (OAuth2 + X-API-Key, cached token)
  data/              obd_codes.json — vendored generic DTC descriptions
  migrations/        Numbered SQL files (001_initial.sql, …)
  domain/            Plain dataclasses: Garage, Vehicle, ServiceLog, OdometerLog, Photo, User
  repositories/      GarageRepository, VehicleRepository, ServiceLogRepository,
                     OdometerLogRepository, PhotoRepository, UserRepository — own all SQL
  routes/            Flask Blueprints: admin, auth, garages, vehicles, services, odometer,
                     mot, photos, codes, export (services CSV/TSV/JSON), search, users
```

- **Adding a schema change:** drop a new `NNN_description.sql` in `migrations/`. It runs automatically on next startup and is recorded in `schema_migrations`.
- **Adding an endpoint:** add a method to the relevant repository, call it from the relevant blueprint.
- **Auth:** Flask-Login guards all routes via `@login_required`; a `before_request` hook in `__init__.py` enforces account expiry (logs the user out). Read-only is per-garage and enforced in routes via `torqued.access`.
- **Tenancy:** collection endpoints accept an optional `garage_id` query param and otherwise return data for all the user's garages; item endpoints resolve the garage through the vehicle. Out-of-scope resources return 404, write attempts by readonly members return 403.
- **Version history:** vehicles and service logs snapshot to `*_history` tables on every create/update; `revert` endpoints restore a snapshot.
- **Admin-only:** `routes/admin.py` exposes `/api/admin/pythonanywhere` (CPU, web app, scheduled task info) — gated on `current_user.is_admin`. Requires `PA_API_TOKEN` and `PA_USERNAME` env vars.

### Frontend (`frontend-src/`)

```
App.jsx              Shell: checks auth state, renders LoginPage or the main layout (sidebar + bottom nav)
AuthContext.jsx      Provides user (incl. memberships), garages, currentGarage +
                     selectGarage (persisted to localStorage), roleFor(garageId)
api.js               Thin fetch wrapper (JSON + multipart upload); all calls use credentials: 'include'
units.js             mi/km + psi/bar conversion and formatting
constants.js         FormMode, vehicle kinds, service categories, reminder labels
styles/              Per-concern CSS modules (base, buttons, cards, forms, layout, garage, …)
components/          Pages: Dashboard, VehicleList, VehicleDetail, VehicleForm,
                     ServiceList, ServiceDetail, ServiceForm, CodeLookup, LoginPage,
                     AccountPage, MembersPage (per-garage), AdminPage (site admin:
                     garages + users + PythonAnywhere stats)
                     Shared: PhotoGallery, MotCard, FaultCodeInput, SuggestInput, ExportDropdown,
                     PythonAnywhereStats, RelativeTime, Skeleton, BuildInfo, Toast
```

- **PhotoGallery** — grid + lightbox + caption editing; uploads multipart to `/api/vehicles/<id>/photos` (optionally scoped to a service log).
- **VehicleDetail** — reminders, info card, tyre pressures (psi & bar), editable spec list, mileage card (interactive chart with per-point source tooltips + quick add), MOT history card (DVSA refresh, summary tiles, per-test defects), service history, photos, version history.
- **Garage switcher** — in the sidebar (and mobile More menu); list pages (Dashboard, VehicleList, ServiceList) are scoped to `currentGarage`, detail pages derive the role from the resource's `garage_id` via `roleFor`.
- **AdminPage** — site-admin page at `/admin`: create/rename/delete garages, create/delete users (optionally assigning a garage + role), PythonAnywhere stats. **MembersPage** at `/members`: members of the current garage; garage owners add/remove members and change roles.

## Running locally

```bash
make run            # start both services
make stop           # stop
make logs           # tail logs (make logs service=backend for one service)
make build          # rebuild images (needed after requirements.txt or Dockerfile changes)
make build-frontend # compile React into dist/ (for local production preview)
```

### Database & users

```bash
make migrate                                       # apply any pending migrations
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

### Dev tooling

```bash
make format            # ruff format the backend
make lint-backend      # ruff check + mypy
make lint-frontend     # eslint
make test-backend      # pytest with 100% coverage gate (see pyproject.toml)
make test-frontend     # vitest
make test              # all of the above (mirrors CI)
```

The database is at `data/garage.db` and uploaded photos in `data/uploads/` (both bind-mounted into the backend container).

## PythonAnywhere deployment

```bash
make deploy-pa    # checkout deploy branch, reset to origin/deploy, create venv if needed, install deps
```

All `make` commands listed under **Database & users** above auto-detect the environment: on PythonAnywhere they run via `venv/bin/python backend-src/manage.py` directly; locally they go through Docker. Detection uses `PYTHONANYWHERE_SITE`, an env var PythonAnywhere injects automatically into every console and web process (set to the site's domain, e.g. `username.pythonanywhere.com`).

See [DEPLOYMENT.md](DEPLOYMENT.md) for first-time setup.

## Key conventions

- Commit format: `feat/fix/chore(component): one-line description`
- Small, focused commits — never bulk everything together
- Never commit or push without explicit instruction
- Backend changes that don't touch `requirements.txt` or `Dockerfile.backend` hot-reload via the bind mount — no rebuild needed
- Frontend changes hot-reload via Vite — no rebuild needed
