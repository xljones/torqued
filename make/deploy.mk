# ── PythonAnywhere deployment ────────────────────────────────────────────────
# Run from a PythonAnywhere Bash console inside ~/torqued

.PHONY: deploy-pa
# pull latest deploy branch (includes built dist/), install deps, migrate the DB, reload, summarise
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
	# Reload the web app so the long-running WSGI process picks up the new Python code.
	# (The served dist/ refreshes on its own, but route/code changes need this reload.)
	touch /var/www/$$(echo "$$PYTHONANYWHERE_SITE" | tr . _)_wsgi.py
	@python3 scripts/deploy_summary.py
