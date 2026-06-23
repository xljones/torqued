# Deployment — Torqued on PythonAnywhere

The app is served from a single PythonAnywhere web app. Flask serves the built React frontend (`dist/`) and the JSON API.

The **`deploy` branch** mirrors `main` and includes the pre-built `dist/` directory. CI rebuilds and force-pushes it on every push to `main`.

## First-time setup

### 1. Clone the repo

Open a **Bash console** on PythonAnywhere and clone the `deploy` branch into your home directory:

```bash
git clone --branch deploy https://github.com/xljones/torqued.git
cd torqued
```

### 2. Install dependencies

```bash
make deploy-pa
```

This resets to the latest `origin/deploy`, creates `venv/` if missing, and installs `requirements.txt`. It also runs after every code update — see [Updating a deployment](#updating-a-deployment).

### 3. Create your `.env` file

The backend connects to **PostgreSQL** via `DATABASE_URL` (SQLAlchemy URL with the
psycopg v3 driver). Provision a database first (PythonAnywhere offers Postgres, or use
any external/managed Postgres), then:

```bash
cat > .env <<EOF
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
FLASK_DEBUG=0
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/torqued
EOF
```

Replace `USER`, `PASSWORD`, `HOST`, and the database name with your credentials. (If
`DATABASE_URL` is omitted the app falls back to a local SQLite file at
`data/garage.db` — fine for a quick try, but use Postgres for a real deployment.)

`.env` is gitignored and will not be overwritten by `make deploy-pa`. See
[.env.example](.env.example) for the full list of supported variables.

**Optional — admin panel PythonAnywhere stats.** If you want the admin panel to show live PythonAnywhere CPU / web app / scheduled task info, add a [PythonAnywhere API token](https://www.pythonanywhere.com/account/#api_token) and your PythonAnywhere username:

```bash
echo "PA_API_TOKEN=<your-token>" >> .env
echo "PA_USERNAME=<your-username>" >> .env
```

**Optional — admin panel Neon database stats.** If your database is hosted on [Neon](https://neon.tech) and you want the admin panel to show live storage / compute usage, add a [Neon API key](https://console.neon.tech/app/settings/api-keys) (the project id is optional — the first project on the key is used when omitted):

```bash
echo "NEON_API_KEY=<your-api-key>" >> .env
echo "NEON_PROJECT_ID=<your-project-id>" >> .env       # optional
echo "NEON_COMPUTE_LIMIT_HOURS=100" >> .env            # optional — your plan's monthly compute-hours
```

Storage shows as a percentage of Neon's reported size limit automatically. Compute has no plan-inherent limit, so to show it as a percentage set `NEON_COMPUTE_LIMIT_HOURS` to your plan's monthly compute-hours allowance (the Free plan includes ≈100); otherwise the card shows a plain compute-hours figure.

**Optional — DVSA MOT history.** To enable the "Refresh from DVSA" button on vehicle pages, [register for the MOT history API](https://documentation.history.mot.api.gov.uk/mot-history-api/register) (free for under 500,000 requests/year; DVSA emails credentials in 1–5 working days) and add:

```bash
echo "MOT_CLIENT_ID=<client-id>" >> .env
echo "MOT_CLIENT_SECRET=<client-secret>" >> .env
echo "MOT_TOKEN_URL=https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/token" >> .env
echo "MOT_API_KEY=<api-key>" >> .env
```

### 4. Create your first user

```bash
make create-admin username=<username> password=<password>
```

To list existing users at any time:

```bash
make list-users
```

### 5. Configure the web app

In the **PythonAnywhere Web tab**:

| Setting | Value |
|---|---|
| Source code | `/home/<you>/torqued` |
| Working directory | `/home/<you>/torqued` |
| Virtualenv | `/home/<you>/torqued/venv` |

**WSGI configuration file** — replace the entire contents with the contents of `pa_wsgi.py` from the repo. (It loads `.env`, adds `backend-src/` to `sys.path`, and imports `application` from `wsgi.py`.)

### 6. Reload

Hit **Reload** in the Web tab. The app will be live at `https://<you>.pythonanywhere.com`.

The schema is created and kept current automatically: `run_migrations()` (Alembic `upgrade head`) runs against your `DATABASE_URL` on every app startup.

---

## Updating a deployment

From a **PythonAnywhere Bash console** inside `~/torqued`:

```bash
make deploy-pa
```

This switches to the `deploy` branch, pulls the latest changes (including the freshly built `dist/`), installs any new Python dependencies, **backs up the database** and then **runs database migrations** (both behind a brief maintenance page — see below). The backup (`manage.py db-backup --keep 3`) is a pre-migration rollback point written to `data/db-backup-<timestamp>.sql`; `--keep 3` prunes all but the 3 newest so you always have the last few deploys' snapshots without the directory growing unbounded. Restore one with `make db-restore file=db-backup-<timestamp>.sql` if a migration goes wrong. Then reload the web app from the PythonAnywhere Web tab to apply the new code.

> If the backup or a migration fails, the `MAINTENANCE` flag is left in place so the site keeps showing the maintenance page rather than serving against a half-migrated schema. Fix the issue and re-run `make deploy-pa`, or remove the flag with `rm MAINTENANCE` once resolved.

### Automatic redeploy on merge to `main` (optional)

CI can call a webhook on the site to run the deploy for you, so a merge to `main` redeploys without a console visit. The webhook (`POST /api/deploy/webhook`) verifies an HMAC-SHA256 signature, then runs the **same** `scripts/deploy_pa.sh` that `make deploy-pa` runs — in a detached process, so the WSGI reload at the end of the deploy doesn't kill the request. It is inert (returns 404) unless explicitly enabled.

To turn it on:

1. **Generate a dedicated secret** (not `SECRET_KEY`): `openssl rand -hex 32`.
2. **PythonAnywhere `~/torqued/.env`:** add `ENABLE_DEPLOY_WEBHOOK=1` and `DEPLOY_WEBHOOK_SECRET=<that secret>`, then reload the web app once so it picks them up.
3. **GitHub → repo Settings → Secrets and variables → Actions:** add `DEPLOY_WEBHOOK_SECRET` (the same value) and `DEPLOY_WEBHOOK_URL` (`https://<you>.pythonanywhere.com/api/deploy/webhook`).

The CI `deploy` job builds and pushes the `deploy` branch as before, then signs and POSTs to the webhook. If either GitHub secret is unset the step no-ops, so this stays optional. Progress and any errors are appended to `~/torqued/deploy-webhook.log` (override with `DEPLOY_LOG_FILE`). The migration-failure behaviour above still applies — a failed migration leaves the `MAINTENANCE` page up.

> **Reliability note:** the detached deploy process is killed when the WSGI worker reloads (PythonAnywhere recycles a worker's children on reload), but the reload is the deploy's *last* step, so git/pip/migrate have already finished — only the cosmetic summary tail may be truncated. After enabling, confirm one real merge fully redeploys (site comes back on the new SHA, `deploy-webhook.log` shows the migration finishing).

---

## Database management

All commands below work on both PythonAnywhere and locally — they auto-detect the environment based on the `PYTHONANYWHERE_SITE` env var that PythonAnywhere injects into every console and web process.

```bash
make migrate                                       # apply pending migrations (default DB)
make migrate prod=1                                # ...against the production DB (PROD_DATABASE_URL)
make seed                                          # populate sample data
make reset-db                                      # drop all tables — including users (interactive confirm)

make db-backup                                     # write data/db-backup-<timestamp>.sql
make db-restore file=db-backup-<timestamp>.sql     # restore from backup (interactive confirm)

make create-user  username=x password=y            # normal user
make create-admin username=x password=y            # admin user
make rename-user  username=x new_username=y
make delete-user  username=x                       # interactive confirm
make list-users
```

**Targeting production from your laptop.** Append `prod=1` to any command above except
`seed` to run it against the production database (`PROD_DATABASE_URL`) instead of the local
one — e.g. `make create-admin username=x password=y prod=1`, `make list-users prod=1`,
`make db-backup prod=1`. A `⚠ Targeting the PRODUCTION database at <host>` line is printed
first, and the destructive commands (`reset-db`, `db-restore`, `delete-user`) still prompt
for confirmation. (On PythonAnywhere `DATABASE_URL` already is production, so you don't pass
`prod=1` there — and it errors, since there's no separate `PROD_DATABASE_URL`.)

`migrate` runs Alembic (`upgrade head`); `reset-db` drops and recreates the schema.
For a Postgres database, `db-backup` / `db-restore` shell out to `pg_dump` / `psql`, so
those client tools must be on `PATH` (they ship in the backend Docker image; on
PythonAnywhere install or use the bundled `postgresql-client`).

---

## Hosted Postgres (Neon, Supabase, …)

A managed Postgres connection string works as-is — paste the one your provider gives
you into `DATABASE_URL`. Using **Neon** as the example:

- **Driver & SSL.** Neon hands you `postgresql://…?sslmode=require&channel_binding=require`.
  You don't need to add `+psycopg`: the app pins the psycopg v3 driver automatically, and
  the `sslmode` / `channel_binding` query params are passed straight through to libpq.
- **Pooled vs direct endpoint.** Neon exposes a direct host and a pooled host (the one with
  `-pooler` in the hostname). Both work — the app disables psycopg's server-side prepared
  statements so it is safe behind the transaction pooler. Use the **pooled** endpoint for the
  running app; either endpoint is fine for migrations (Neon recommends the **direct** one for
  schema changes).

### Running migrations against Neon

Migrations are ordinary Alembic — `run_migrations()` is just `alembic upgrade head`. Pick
whichever fits your flow:

1. **As part of the deploy.** `make deploy-pa` runs the migration (against `DATABASE_URL`,
   which is Neon on PythonAnywhere) behind a maintenance page before you reload — see
   [Updating a deployment](#updating-a-deployment). `create_app()` also runs migrations on
   boot as a safety net.
2. **From your laptop, targeting production.** Put the Neon URL in `PROD_DATABASE_URL` (the
   same var the dev DB switcher uses; the direct endpoint is the safe choice for schema
   changes) and run:

   ```bash
   make migrate prod=1        # = manage.py migrate --prod = alembic upgrade head on PROD_DATABASE_URL
   ```

   Useful to push schema changes to prod ahead of (or without) a full code deploy, or to gate
   migrations in CI before the app rolls out.
