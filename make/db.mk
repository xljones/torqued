# Most database / user commands accept an optional `prod=1` flag to run against the
# production database (PROD_DATABASE_URL) instead of the local one, e.g.
#   make create-admin username=x password=y prod=1
# `seed` is intentionally local-only (it inserts demo data). On PythonAnywhere
# DATABASE_URL already is production, so the flag isn't needed (and errors) there.
PROD_FLAG = $(if $(prod),--prod,)

.PHONY: migrate
# run pending migrations: make migrate [prod=1]
migrate:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py migrate $(PROD_FLAG)
else
	docker compose run --rm backend python manage.py migrate $(PROD_FLAG)
endif

.PHONY: create-user
# create a normal user: make create-user username=<name> password=<pass> [prod=1]
create-user:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py create-user $(username) $(password) $(PROD_FLAG)
else
	docker compose run --rm backend python manage.py create-user $(username) $(password) $(PROD_FLAG)
endif

.PHONY: create-garage
# create a garage: make create-garage name=<name> [prod=1]
create-garage:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py create-garage "$(name)" $(PROD_FLAG)
else
	docker compose run --rm backend python manage.py create-garage "$(name)" $(PROD_FLAG)
endif

.PHONY: add-member
# add a user to a garage: make add-member garage=<name> username=<user> role=<owner|member|readonly> [prod=1]
add-member:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py add-member "$(garage)" $(username) $(or $(role),member) $(PROD_FLAG)
else
	docker compose run --rm backend python manage.py add-member "$(garage)" $(username) $(or $(role),member) $(PROD_FLAG)
endif

.PHONY: create-admin
# create an admin user: make create-admin username=<name> password=<pass> [prod=1]
create-admin:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py create-user $(username) $(password) --admin $(PROD_FLAG)
else
	docker compose run --rm backend python manage.py create-user $(username) $(password) --admin $(PROD_FLAG)
endif

.PHONY: rename-user
# rename a user: make rename-user username=<name> new_username=<new-name> [prod=1]
rename-user:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py rename-user $(username) $(new_username) $(PROD_FLAG)
else
	docker compose run --rm backend python manage.py rename-user $(username) $(new_username) $(PROD_FLAG)
endif

.PHONY: delete-user
# delete a user: make delete-user username=<name> [prod=1]  (interactive confirm)
delete-user:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py delete-user $(username) $(PROD_FLAG)
else
	docker compose run --rm -it backend python manage.py delete-user $(username) $(PROD_FLAG)
endif

.PHONY: list-users
# list all users: make list-users [prod=1]
list-users:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py list-users $(PROD_FLAG)
else
	docker compose run --rm backend python manage.py list-users $(PROD_FLAG)
endif

.PHONY: reset-db
# drop all tables — including users (interactive confirm): make reset-db [prod=1]
reset-db:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py reset-db $(PROD_FLAG)
else
	docker compose run --rm -it backend python manage.py reset-db $(PROD_FLAG)
endif

.PHONY: db-backup
# dump the database to data/db-backup-<timestamp>.sql: make db-backup [prod=1]
db-backup:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py db-backup $(PROD_FLAG)
else
	docker compose run --rm backend python manage.py db-backup $(PROD_FLAG)
endif

.PHONY: db-restore
# restore from a backup (interactive confirm): make db-restore file=db-backup-<timestamp>.sql [prod=1]
db-restore:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py db-restore $(file) $(PROD_FLAG)
else
	docker compose run --rm -it backend python manage.py db-restore $(file) $(PROD_FLAG)
endif

.PHONY: seed
# populate the database with sample data (local only — inserts demo data)
seed:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py seed
else
	docker compose run --rm backend python manage.py seed
endif
