#!/usr/bin/env bash
# PythonAnywhere deploy: pull the built `deploy` branch, install deps, migrate behind a
# maintenance page, reload the web app, summarise.
#
# Single source of truth shared by `make deploy-pa` (manual console deploy) and the
# /api/deploy/webhook endpoint (CI-triggered). It cd's to the repo root itself, since the
# webhook spawns it as a detached child with an unknown working directory.
set -euo pipefail

cd "$(dirname "$0")/.."

# Serialise deploys with a lock file (a root flag file like MAINTENANCE). A second deploy
# (two merges in quick succession, or a manual deploy racing the webhook) exits instead of
# interleaving git resets and migrations. `set -o noclobber` makes the create atomic
# (O_EXCL), so the check-and-create can't race; the trap clears the lock on any exit.
LOCK_FILE="DEPLOY_LOCK"
if ! (set -o noclobber; echo "$$" > "$LOCK_FILE") 2>/dev/null; then
	echo "deploy: another deploy is in progress ($LOCK_FILE exists) — aborting" >&2
	exit 1
fi
trap 'rm -f "$LOCK_FILE"' EXIT

echo "deploy: starting $(date -u +%Y-%m-%dT%H:%M:%SZ)"

git fetch origin && git checkout deploy && git reset --hard origin/deploy

[ -d venv ] || python3 -m venv venv
venv/bin/pip install -r requirements.txt

# Show a maintenance page while we back up the database and migrate the schema
# (DATABASE_URL is the production DB on PythonAnywhere). The backup is a pre-migration
# rollback point taken with the site quiesced; only the 3 newest are kept. If the backup
# or the migration fails the flag stays, keeping the site in maintenance until you fix it
# and re-run (or `rm MAINTENANCE`).
touch MAINTENANCE
venv/bin/python backend-src/manage.py db-backup --keep 3
venv/bin/python backend-src/manage.py migrate
rm -f MAINTENANCE

# Reload the web app so the long-running WSGI process picks up the new Python code.
# (The served dist/ refreshes on its own, but route/code changes need this reload.)
touch "/var/www/$(echo "$PYTHONANYWHERE_SITE" | tr . _)_wsgi.py"

python3 scripts/deploy_summary.py
