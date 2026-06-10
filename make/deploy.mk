# ── PythonAnywhere deployment ────────────────────────────────────────────────
# Run from a PythonAnywhere Bash console inside ~/torqued

.PHONY: deploy-pa
# pull latest deploy branch (includes built dist/), create venv if needed, install deps
deploy-pa:
	git fetch origin && git checkout deploy && git reset --hard origin/deploy
	[ -d venv ] || python3 -m venv venv
	venv/bin/pip install -r requirements.txt
	@python3 scripts/deploy_summary.py
