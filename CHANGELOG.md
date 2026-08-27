# Changelog

## [Unreleased]

### Removed
- **Neon database admin card.** The admin panel's Neon storage/compute stats card and its
  `/api/admin/neon` endpoint are gone (the `NEON_*` env vars are no longer read).

### Changed
- **Reminders now warn much earlier by default.** The "due soon" window for service and
  schedule reminders went from 30 days / 500 km to **3 months / 2,000 miles** (the MOT and
  road-tax windows are unchanged at 60 and 30 days). Existing garages pick this up
  immediately with no action: reminders that used to sit quietly as *upcoming* will now show
  amber and count towards the dashboard's "Maintenance due" total. Narrow the window back in
  **Settings → Maintenance reminders** if the old behaviour suited you better.
- **The dashboard's reminders are nested under their vehicle.** The separate "Maintenance
  reminders" list is gone; each vehicle row in *The garage* now carries a count badge and
  expands to show its own reminders, so a reminder no longer has to repeat the vehicle's
  name. Vehicles with anything overdue or due soon start expanded. A **Show N upcoming**
  toggle (remembered per device) hides the low-priority tail — overdue and due-soon
  reminders are always shown.
- **MOT and tax tiles keep their colour on hover.** Hovering the MOT or tax tile on a
  vehicle used to wash it out to grey; it now deepens its own green/amber/red. The tiles
  also gained a visible keyboard focus ring.
- **The DVSA and DVLA records sit side by side.** Expanding a vehicle's MOT tile lays the
  two source records out in two columns (stacking on narrow screens) so they can be read
  against each other rather than scrolled between.

### Added
- **Per-garage reminder windows.** How far ahead a reminder counts as "due soon" is now
  configurable per garage under **Settings → Maintenance reminders** — separately for
  services (days *and* distance, in mi or km), the MOT, and road tax. Only a garage owner
  can change them; other members see the values read-only. Leaving a field blank uses the
  application default. Migration `0009`, `PUT /api/garages/<id>/settings`.
- **Service schedules.** Each vehicle can define recurring service schedules — a *minor*,
  a *major*, and any number of user-named *custom* ones — with an interval expressed as
  every N months and/or every N km/mi (stored canonically in km). A service log can record
  which schedule(s) it fulfilled (many-to-many); the newest fulfilling log is the anchor
  from which the next due date/mileage is projected, and the result surfaces in the
  existing reminder stream (`type='schedule'`, alongside service and MOT reminders) on the
  dashboard, vehicle detail, and PDF report. When logging a service you tick every schedule
  it covers, and because a major service includes the minor, ticking the major auto-ticks
  the minor so it isn't left showing overdue. Migration `0005`.
- **Run DB/user commands against production.** The database and user `make` commands take an
  optional `prod=1` flag (e.g. `make create-admin username=x password=y prod=1`,
  `make migrate prod=1`, `make db-backup prod=1`) to target `PROD_DATABASE_URL` instead of the
  local DB; `manage.py` handles a global `--prod` that repoints `DATABASE_URL` once and prints
  the target host. `seed` stays local-only. `manage.py` also loads the project `.env` so CLI
  commands hit the configured database (previously PythonAnywhere console commands fell back to
  SQLite).
- **Maintenance page on deploy.** `make deploy-pa` now runs migrations before rolling out the
  new code, behind a short maintenance page (a `MAINTENANCE` flag file makes every request
  return a 503 placeholder; a failed migration leaves it in place).
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
  (`pg_dump`/`psql` for Postgres, `sqlite3` dump for SQLite). Hosted Postgres URLs (Supabase,
  Railway, …) work verbatim — the psycopg v3 driver is pinned, `?sslmode=…` is honoured, and
  server-side prepared statements are disabled for transaction-pooler (PgBouncer)
  compatibility. Configure via [.env.example](.env.example); see [DEPLOYMENT.md](DEPLOYMENT.md).
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
