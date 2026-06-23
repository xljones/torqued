# ── PythonAnywhere deployment ────────────────────────────────────────────────
# Run from a PythonAnywhere Bash console inside ~/torqued

.PHONY: deploy-pa
# Pull latest deploy branch (built dist/), install deps, migrate behind a maintenance
# page, reload, summarise. The steps live in scripts/deploy_pa.sh so this manual path and
# the CI-triggered /api/deploy/webhook share one source of truth.
deploy-pa:
	bash scripts/deploy_pa.sh
