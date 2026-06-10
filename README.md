# Torqued

> *All torque, no friction.*

[![CI](https://github.com/xljones/torqued/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/xljones/torqued/actions/workflows/ci.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

A web app for logging vehicle maintenance — built for motorcycles **and** cars. Keep a full service history per vehicle, track mileage with automatic mile/kilometre conversion, store the reference specs you always forget (tyre pressures in psi *and* bar, oil grades, chain slack, torque values), and attach photos to anything.

## Features

- **Garage** — any number of cars and motorcycles, each with make/model/year, registration plate, VIN, and a per-vehicle odometer display unit (mi or km, converted automatically everywhere)
- **Service log** — what was done, who did it (with autocomplete from past entries), when, at what mileage, and what it cost
- **Maintenance reminders** — set "next due" by date and/or odometer on any service; the dashboard flags overdue and due-soon work, and newer services in the same category close old reminders automatically
- **Mileage tracking** — quick odometer entries plus readings captured from services, merged into one timeline with a sparkline
- **Reference specs** — dedicated tyre pressure card (psi/bar) and tyre sizes, plus free-form per-vehicle specs (oil type & capacity, battery, wheel-nut torque, …)
- **Photos** — upload photos against a vehicle or a specific service; gallery with lightbox and captions
- **Version history** — every save of a vehicle or service is snapshotted; revert at any time
- **Export** — service history as CSV, TSV, or JSON (whole fleet or per vehicle)
- **Archiving** — sold a vehicle? Archive it; history is kept but it leaves the garage view
- **Users & roles** — session login (Flask-Login); admins, normal users, read-only users, and optional account expiry
- **Admin panel** — manage users; view live PythonAnywhere CPU, web app, and scheduled task info

## Running locally

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
# Start the app
make run

# Create your first user (use create-admin for an admin account)
make create-user username=you password=yourpassword

# Populate with sample data (3 vehicles, 9 services, 4 odometer logs)
make seed

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
    migrations/        Versioned SQL files
    domain/            Vehicle, ServiceLog, OdometerLog, Photo, User dataclasses
    repositories/      All SQL per entity
    routes/            Flask Blueprints (admin, auth, vehicles, services,
                       odometer, photos, export, search, users)

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
