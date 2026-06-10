# ── Dev tooling ──────────────────────────────────────────────────────────────
# Requires: make build (rebuilds backend image with dev deps)

.PHONY: format
# format the Python backend with ruff
format:
	docker compose run --rm backend ruff format torqued/

.PHONY: lint-backend
# lint the Python backend with ruff
lint-backend: backend-typecheck
	docker compose run --rm backend ruff check torqued/

.PHONY: backend-typecheck
# type-check the Python backend with mypy
backend-typecheck:
	docker compose run --rm backend mypy torqued/

.PHONY: test-backend
# run Python backend tests with pytest (coverage config in pyproject.toml)
test-backend:
	docker compose run --rm backend pytest tests/ -v

.PHONY: lint-frontend
# lint the frontend with eslint
lint-frontend:
	docker compose run --rm frontend npm run lint

.PHONY: test-frontend
# run frontend tests with vitest
test-frontend:
	docker compose run --rm frontend npm run test

.PHONY: test
# lint, typecheck, and test backend and frontend (mirrors CI)
test: lint-backend test-backend lint-frontend test-frontend
