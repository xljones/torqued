# Torqued — Claude Context

> A web app for logging vehicle maintenance (motorcycles & cars). *All torque, no friction.*

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

- **Vehicle** — car or motorcycle; has a per-vehicle odometer display unit (`mi`/`km`), tyre sizes/pressures, free-form key/value **specs**, and an `archived` flag.
- **ServiceLog** — one maintenance event (date, title, category, performed_by, cost, odometer, optional `next_due_date`/`next_due_km`).
- **OdometerLog** — manual mileage reading. Mileage timelines and "latest odometer" merge these with service-log readings.
- **Photo** — upload attached to a vehicle, optionally scoped to a service log. Files live in `data/uploads/` (env `UPLOAD_DIR`), records in the `photos` table.
- **Reminders** are derived, not stored: any service log with a `next_due_*` value creates one until a newer log in the same category exists. Status is `overdue` / `due_soon` (≤30 days or ≤500 km away) / `upcoming`.

**Units:** distances are stored canonically in **km** (`odometer_km`, `next_due_km`) along with the unit the user typed; tyre pressures are stored in **psi**. Conversion helpers: `torqued/units.py` (backend), `frontend-src/units.js` (frontend, incl. psi↔bar).

## Architecture

### Backend (`backend-src/`)

DDD-inspired layering — routes never write SQL directly.

```
torqued/
  __init__.py        create_app() factory; Flask-Login setup, before_request auth guard
  db.py              get_db(), run_migrations() — migration runner reads migrations/*.sql
  units.py           mi/km conversion + request payload parsing
  migrations/        Numbered SQL files (001_initial.sql, …)
  domain/            Plain dataclasses: Vehicle, ServiceLog, OdometerLog, Photo, User
  repositories/      VehicleRepository, ServiceLogRepository, OdometerLogRepository,
                     PhotoRepository, UserRepository — own all SQL
  routes/            Flask Blueprints: admin, auth, vehicles, services, odometer,
                     photos, export (services CSV/TSV/JSON), search, users
```

- **Adding a schema change:** drop a new `NNN_description.sql` in `migrations/`. It runs automatically on next startup and is recorded in `schema_migrations`.
- **Adding an endpoint:** add a method to the relevant repository, call it from the relevant blueprint.
- **Auth:** Flask-Login guards all routes via `@login_required`; an additional `before_request` hook in `__init__.py` enforces account expiry (logs the user out) and read-only mode (blocks non-GET writes except password change / logout).
- **Version history:** vehicles and service logs snapshot to `*_history` tables on every create/update; `revert` endpoints restore a snapshot.
- **Admin-only:** `routes/admin.py` exposes `/api/admin/pythonanywhere` (CPU, web app, scheduled task info) — gated on `current_user.is_admin`. Requires `PA_API_TOKEN` and `PA_USERNAME` env vars.

### Frontend (`frontend-src/`)

```
App.jsx              Shell: checks auth state, renders LoginPage or the main layout (sidebar + bottom nav)
AuthContext.jsx      Provides user, login(), logout() via React context
api.js               Thin fetch wrapper (JSON + multipart upload); all calls use credentials: 'include'
units.js             mi/km + psi/bar conversion and formatting
constants.js         FormMode, vehicle kinds, service categories, reminder labels
styles/              Per-concern CSS modules (base, buttons, cards, forms, layout, garage, …)
components/          Pages: Dashboard, VehicleList, VehicleDetail, VehicleForm,
                     ServiceList, ServiceDetail, ServiceForm, LoginPage,
                     AccountPage, UserList (admin panel)
                     Shared: PhotoGallery, SuggestInput, ExportDropdown,
                     PythonAnywhereStats, RelativeTime, Skeleton, BuildInfo, Toast
```

- **PhotoGallery** — grid + lightbox + caption editing; uploads multipart to `/api/vehicles/<id>/photos` (optionally scoped to a service log).
- **VehicleDetail** — reminders, info card, tyre pressures (psi & bar), editable spec list, mileage card (sparkline + quick add), service history, photos, version history.
- **UserList** — admin-only page mounted at `/admin`; manages users and embeds `PythonAnywhereStats`.

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
make seed                                          # populate sample data (3 vehicles, 9 services)
make reset-db                                      # drop all tables (interactive confirm) — including users
make db-backup                                     # write data/db-backup-<timestamp>.sql
make db-restore file=db-backup-<timestamp>.sql     # restore from backup (interactive confirm)

make create-user  username=x password=y            # normal user
make create-admin username=x password=y            # admin user
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
