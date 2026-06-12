# Torqued

> *All torque, no friction.*

[![CI](https://github.com/xljones/torqued/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/xljones/torqued/actions/workflows/ci.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

A multi-tenant web app for logging vehicle maintenance — built for motorcycles **and** cars. Vehicles live in **garages**; users can belong to any number of garages with a per-garage role (owner / member / read-only). Keep a full service history per vehicle, track mileage with automatic mile/kilometre conversion, store the reference specs you always forget (tyre pressures in psi *and* bar, oil grades, chain slack, torque values), and attach photos to anything.

## Features

- **Garages (multi-tenant)** — data is split per garage; a garage switcher in the sidebar flips the whole app between them. Site admins create garages and users; garage owners manage their garage's members and roles
- **Per-garage roles** — `owner` (manage members, rename), `member` (full read-write), `readonly` (view only); enforced on every endpoint
- **Vehicles** — any number of cars and motorcycles per garage, each with make/model/year, registration plate, VIN, and a per-vehicle odometer display unit (mi or km, converted automatically everywhere)
- **Service log** — what was done, who did it (with autocomplete from past entries), when, at what mileage, and what it cost
- **Maintenance reminders** — set "next due" by date and/or odometer on any service; the dashboard flags overdue and due-soon work, and newer services in the same category close old reminders automatically
- **Mileage tracking** — quick odometer entries, readings captured from services, and MOT-recorded mileages merged into one timeline; an interactive chart plots every reading with a hover tooltip showing the mileage, date and where it came from
- **MOT history (UK)** — pull a vehicle's official DVSA test history by registration plate: pass/fail results, expiry dates, defects and advisories, outstanding recalls; recorded mileages feed straight into the mileage timeline (needs free [DVSA MOT history API](https://documentation.history.mot.api.gov.uk/) credentials; full response schema in [docs/MOT_API.md](docs/MOT_API.md))
- **Reference specs** — dedicated tyre pressure card (psi/bar) and tyre sizes, plus free-form per-vehicle specs (oil type & capacity, battery, wheel-nut torque, …)
- **Photos** — upload photos against a vehicle or a specific service; gallery with lightbox and captions
- **Fault code lookup** — type an OBD-II code (e.g. `P0016`) for an instant description, or search 2,100+ generic codes by keyword; unknown manufacturer-specific codes still get a structural breakdown (system / scope / subsystem)
- **Version history** — every save of a vehicle or service is snapshotted; revert at any time
- **Export** — service history as CSV, TSV, or JSON (whole fleet or per vehicle)
- **Archiving** — sold a vehicle? Archive it; history is kept but it leaves the garage view
- **Users** — session login (Flask-Login) with optional account expiry; site admins manage users and garages from the admin panel (plus live PythonAnywhere stats)

## Running locally

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
# Start the app
make run

# Create your first user — a site admin can create garages/users from the UI
make create-admin username=you password=yourpassword

# Populate with sample data (1 garage, 3 vehicles, 9 services, 4 odometer logs)
make seed

# Optional: garages & membership from the CLI
make create-garage name="Home Garage"
make add-member garage="Home Garage" username=you role=owner

# Drop all tables — including users (interactive confirm)
make reset-db

# View logs (optionally: make logs service=backend)
make logs

# Stop
make stop
```

App runs at **http://localhost:5173**.

### Dev tooling

```bash
make test           # lint + typecheck + test (backend & frontend) — mirrors CI
make format         # ruff format the backend
make build-frontend # compile the React app into dist/
```

See `make/` for the full set of targets (database backup/restore, user management, individual lint/test steps, etc.).

## Project structure

```
backend-src/           Python backend
  app.py               Local dev entry point
  manage.py            CLI (create-user, migrate, seed, db-backup, db-restore, …)
  wsgi.py              WSGI entry point (used by pa_wsgi.py)
  torqued/
    __init__.py        App factory (Flask-Login, before_request auth/expiry/readonly guard)
    db.py              Connection + migration runner
    units.py           mi/km and psi/bar conversion helpers
    dtc.py             OBD-II fault code lookup (data/obd_codes.json, MIT-licensed dataset)
    mot.py             DVSA MOT history API client (OAuth2 client credentials)
    migrations/        Versioned SQL files
    access.py          Per-garage role checks (owner / member / readonly)
    domain/            Garage, Vehicle, ServiceLog, OdometerLog, Photo, User dataclasses
    repositories/      All SQL per entity
    routes/            Flask Blueprints (admin, auth, garages, vehicles, services,
                       odometer, mot, photos, codes, export, search, users)

frontend-src/          React + Vite frontend
  App.jsx              Router and auth shell (sidebar + bottom nav)
  AuthContext.jsx      Session state
  api.js               Fetch wrapper (JSON + multipart photo upload)
  units.js             Frontend unit conversion / formatting helpers
  constants.js         Shared frontend constants
  styles/              Per-concern CSS modules
  components/          One file per page/component (includes admin UserList + PythonAnywhereStats)

make/                  Modular Makefile (local, db, test, deploy)
scripts/               Deploy/build helper scripts
pa_wsgi.py             PythonAnywhere WSGI shim (loads .env, imports backend-src/wsgi.py)
pyproject.toml         Ruff, mypy, pytest config; project version

data/                  SQLite database + uploaded photos (gitignored)
dist/                  Built frontend (gitignored)
```

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for PythonAnywhere setup instructions.
