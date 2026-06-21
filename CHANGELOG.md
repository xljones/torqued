# Changelog

## [Unreleased]

### Added
- **Dev-only login database switcher.** In development (`FLASK_DEBUG=1`) with
  `PROD_DATABASE_URL` set, the login page offers a Local/Production toggle so you can sign
  in against either the local Postgres container or the real production database without a
  restart. The choice is stored in the signed session and a per-request resolver routes the
  backend accordingly; a red "PRODUCTION" banner shows while you're connected to it. The
  switch is completely inert in a real deployment (gated on dev mode + the env var). See
  [.env.example](.env.example).
- Vehicle history **PDF export**: a rich, printable report covering details, tyres,
  specs, reminders, mileage (with chart), full service history (incl. fault codes),
  and MOT history. Photos are opt-in via an "Include photos" toggle in the vehicle's
  Export dropdown (`GET /api/export/vehicles/<id>/pdf?include_photos=1`).
- **Fault codes** page now lists every code before you search — an empty/blank `q` on
  `GET /api/codes` returns the full list (non-empty searches stay capped at 25).
- **Mileage chart** marks year boundaries (a dashed guide + label at each Jan 1 in span).
- **Odometer quick-add** warns when a reading would go backwards relative to a
  dated neighbour, and shows the vehicle's fixed display unit instead of a unit selector.
- **Service log** can be filtered by a specific vehicle alongside the text filter.
- **Vehicle edit form** splits each DVSA-backed identity field into a two-thirds editable
  override beside the one-third fixed DVSA baseline value, with a green border on the
  value that wins.
- **PDF report** appends "cc" to bare DVSA engine-size numbers, mirroring the web UI.

### Changed
- **Database migrated from SQLite to PostgreSQL.** The backend now talks to its database
  through SQLAlchemy Core (psycopg v3 driver) and is database-agnostic: PostgreSQL in
  development (a `db` service in Docker Compose) and production, SQLite in the test suite,
  selected by `DATABASE_URL` / `DB_PATH`. Repositories keep their `execute("… ? …", (args,))`
  style via a thin dialect-aware `Connection` wrapper. Schema is now managed by **Alembic**
  (`backend-src/migrations/`) instead of the bespoke SQL-file runner; `run_migrations()` runs
  `alembic upgrade head` on startup. `make db-backup` / `db-restore` detect the backend
  (`pg_dump`/`psql` for Postgres, `sqlite3` dump for SQLite). Hosted Postgres URLs (Neon,
  Supabase, …) work verbatim — the psycopg v3 driver is pinned, `?sslmode=…` is honoured, and
  server-side prepared statements are disabled for transaction-pooler (PgBouncer / Neon
  `-pooler`) compatibility. Configure via [.env.example](.env.example); see [DEPLOYMENT.md](DEPLOYMENT.md).
- `RelativeTime` renders future dates in human-friendly units (e.g. MOT expiry reads
  "next month" rather than "in 3,043,741 seconds"); the MOT card shows expiry relatively.

### Removed
- Per-garage **Members page** — garage membership management now lives in the admin
  panel's Users section (site admins add/remove memberships and change roles per user).

## [2.0.0] — 2026-06-11

### Changed
- **Multi-tenant re-architecture**: vehicles now live in **garages**. Users belong to
  any number of garages with a per-garage role (owner / member / readonly); all data
  and every endpoint are scoped accordingly. Fresh `001_initial.sql` (clean reset).
- Global read-only accounts replaced by the per-garage `readonly` role
- Sidebar gains a garage switcher; new Members page (garage owners) and Admin page
  (site admins: garages + users)
- CLI: `create-garage`, `add-member`; seed creates a "Home Garage"

## [1.0.0] — 2026-06-10

### Added
- Initial release, based on the [dirtnap](https://github.com/xljones/dirtnap) architecture
- Garage of vehicles (cars & motorcycles) with specs, tyre pressures (psi/bar), and archiving
- Service logs with categories, costs, performers, and version history
- Maintenance reminders derived from per-service "next due" date/odometer
- Mileage tracking with automatic mi/km conversion and sparkline
- Photo uploads on vehicles and services with gallery, lightbox, and captions
- Service history export (CSV/TSV/JSON), search, users & roles, admin panel
- OBD-II fault code lookup (2,100+ generic codes with keyword search; structural
  decode for manufacturer-specific codes)
