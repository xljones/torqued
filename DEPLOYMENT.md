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

```bash
cat > .env <<EOF
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
FLASK_DEBUG=0
EOF
```

`.env` is gitignored and will not be overwritten by `make deploy-pa`.

**Optional — admin panel PythonAnywhere stats.** If you want the admin panel to show live PythonAnywhere CPU / web app / scheduled task info, add a [PythonAnywhere API token](https://www.pythonanywhere.com/account/#api_token) and your PythonAnywhere username:

```bash
echo "PA_API_TOKEN=<your-token>" >> .env
echo "PA_USERNAME=<your-username>" >> .env
```

**Optional — DVSA MOT history.** To enable the "Refresh from DVSA" button on vehicle pages, [register for the MOT history API](https://documentation.history.mot.api.gov.uk/mot-history-api/register) (free for under 500,000 requests/year; DVSA emails credentials in 1–5 working days) and add:

```bash
echo "MOT_CLIENT_ID=<client-id>" >> .env
echo "MOT_CLIENT_SECRET=<client-secret>" >> .env
echo "MOT_TOKEN_URL=https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/token" >> .env
echo "MOT_API_KEY=<api-key>" >> .env
```

**Optional — DVLA road tax.** To populate the tax status / due date tiles on vehicle pages (the same "Refresh from DVSA & DVLA" button), [register for the DVLA Vehicle Enquiry Service API](https://register-for-ves.driver-vehicle-licensing.api.gov.uk/) (free; a separate key from the MOT one above) and add:

```bash
echo "VES_API_KEY=<api-key>" >> .env
# Optional: point at DVLA's UAT sandbox instead of the live endpoint
# echo "VES_API_URL=https://uat.driver-vehicle-licensing.api.gov.uk/vehicle-enquiry/v1/vehicles" >> .env
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

The database is created automatically at `~/torqued/data/garage.db` on first request, and migrations run on every app startup.

---

## Updating a deployment

From a **PythonAnywhere Bash console** inside `~/torqued`:

```bash
make deploy-pa
```

This switches to the `deploy` branch, pulls the latest changes (including the freshly built `dist/`), and installs any new Python dependencies. Reload the web app from the PythonAnywhere Web tab to apply the changes.

Database migrations run automatically on the next request after reload.

---

## Database management

All commands below work on both PythonAnywhere and locally — they auto-detect the environment based on the `PYTHONANYWHERE_SITE` env var that PythonAnywhere injects into every console and web process.

```bash
make migrate                                       # apply pending migrations
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
