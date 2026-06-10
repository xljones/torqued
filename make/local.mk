.PHONY: build
# build docker images
build:
	docker compose build

.PHONY: run
# start all services (detached)
run:
	docker compose up --force-recreate --detach --remove-orphans

.PHONY: stop
# stop all services
stop:
	docker compose down

.PHONY: logs
# follow logs (optionally: make logs service=backend)
logs:
	docker compose logs -f $(service)

.PHONY: build-frontend
# compile the React app into dist/ (for production / PythonAnywhere)
build-frontend:
	docker compose run --rm frontend npm run build
