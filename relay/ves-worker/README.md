# Torqued DVLA VES relay (Cloudflare Worker)

A tiny Cloudflare Worker that runs the gov.uk **vehicle-enquiry** scrape and returns the
same snapshot JSON `torqued/ves.py::fetch_ves` produces (tax + MOT status + the vehicle
profile). It exists to work around an outbound **egress whitelist**: on a free
PythonAnywhere account all outbound traffic goes through a proxy that only allows
whitelisted hosts, and `vehicleenquiry.service.gov.uk` is **not** on it (so a VES refresh
fails in prod with `Tunnel connection failed: 403 Forbidden`) while `*.workers.dev` **is**.
Cloudflare itself has no such whitelist, so the Worker can reach gov.uk and the app reaches
the Worker.

Full background: [`../../docs/VES_API.md`](../../docs/VES_API.md) → "Production relay".

## Contract

```
GET /ves/<REG>
Authorization: Bearer <RELAY_TOKEN>

200  { registration, tax_status, tax_due_date, mot_status, mot_expiry_date,
       make, colour, date_of_first_registration, year_of_manufacture, cylinder_capacity,
       co2_emissions, fuel_type, euro_status, real_driving_emissions, export_marker,
       type_approval, wheelplan, revenue_weight, date_of_last_v5c }
     # dates null for SORN/untaxed (tax) or no-MOT vehicles; any profile field null if absent
404  { "error": "No vehicle found for registration <REG>" }   # unknown plate
401  { "error": "Unauthorized" }                               # missing/wrong bearer token
502  { "error": "..." }                                         # scrape/flow failure
```

`fetch_ves` maps these statuses straight onto `VesError` (404 → not-found, else 502), so
the app behaves exactly as it does with the direct scrape.

## Deploy

Needs a (free) Cloudflare account and [`wrangler`](https://developers.cloudflare.com/workers/wrangler/).

```bash
cd relay/ves-worker
npx wrangler login
npx wrangler secret put RELAY_TOKEN     # paste a long random string — this is the shared secret
npx wrangler deploy                     # prints https://torqued-ves.<your-subdomain>.workers.dev
```

Then, on the app host (PythonAnywhere `~/torqued/.env`):

```
VES_RELAY_URL=https://torqued-ves.<your-subdomain>.workers.dev
VES_RELAY_TOKEN=<the same random string>
```

and reload the web app. Leave `VES_RELAY_URL` **unset** locally — dev keeps scraping
gov.uk directly.

## Verify

```bash
npx wrangler dev        # local, on http://localhost:8787
curl -H "Authorization: Bearer <token>" http://localhost:8787/ves/<REG>

# after deploy:
curl -H "Authorization: Bearer <token>" https://torqued-ves.<subdomain>.workers.dev/ves/<REG>
```

A taxed vehicle returns a `tax_due_date`; a SORN/untaxed one returns `null`. A vehicle with
an MOT returns `mot_status` + `mot_expiry_date`.

## Maintenance

This is a **mirror** of the scraper in `torqued/ves.py` — the selectors (the
`authenticity_token` form, the `#vehicleStatus` / profile `<dd>` rows, the
`#tax-status-panel` / `#mot-status-panel` / `#mot_hidden_details` reads) are the same ones
documented in `docs/VES_API.md`. When gov.uk changes its markup, fix `ves.py` first (it has
the tests + debug recipe), then mirror the selector change in `src/index.js`.
