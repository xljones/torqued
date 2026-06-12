# Changelog

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
