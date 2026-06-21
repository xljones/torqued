# ── PythonAnywhere deployment ────────────────────────────────────────────────
# Run from a PythonAnywhere Bash console inside ~/torqued

.PHONY: deploy-pa
# pull latest deploy branch (includes built dist/), install deps, migrate the DB, summarise
deploy-pa:
	git fetch origin && git checkout deploy && git reset --hard origin/deploy
	[ -d venv ] || python3 -m venv venv
	venv/bin/pip install -r requirements.txt
	# Show a maintenance page while the schema is migrated (DATABASE_URL is the
	# production DB on PythonAnywhere). If migration fails the flag stays, keeping
	# the site in maintenance until you fix it and re-run (or `rm MAINTENANCE`).
	touch MAINTENANCE
	venv/bin/python backend-src/manage.py migrate
	rm -f MAINTENANCE
	@python3 scripts/deploy_summary.py
